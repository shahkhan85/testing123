#!/usr/bin/env python3
"""
WebSocket Traffic Decoder
Captures and decodes WebSocket frames from live network traffic or pcap files.
Requires: pip3 install scapy
Live capture requires root: sudo python3 websocket_decoder.py
"""

import struct
import argparse
import sys
from datetime import datetime

try:
    from scapy.all import sniff, IP, TCP, Raw
except ImportError:
    print("scapy not installed. Run: pip3 install scapy")
    sys.exit(1)


# WebSocket opcodes per RFC 6455
OPCODES = {
    0x0: "CONTINUATION",
    0x1: "TEXT",
    0x2: "BINARY",
    0x8: "CLOSE",
    0x9: "PING",
    0xA: "PONG",
}

COLORS = {
    "reset":  "\033[0m",
    "bold":   "\033[1m",
    "dim":    "\033[2m",
    "red":    "\033[91m",
    "green":  "\033[92m",
    "yellow": "\033[93m",
    "blue":   "\033[94m",
    "cyan":   "\033[96m",
}


def _c(text, *codes):
    return "".join(COLORS[c] for c in codes) + text + COLORS["reset"]


# ---------------------------------------------------------------------------
# WebSocket frame parser
# ---------------------------------------------------------------------------

def parse_ws_frame(data: bytes):
    """
    Parse one WebSocket frame from the front of `data`.
    Returns (frame_dict, bytes_consumed) or (None, 0) if data is incomplete.

    Frame layout (RFC 6455 §5.2):
      Byte 0: FIN(1) RSV1(1) RSV2(1) RSV3(1) opcode(4)
      Byte 1: MASK(1) payload_len(7)
      [2 bytes extended len if payload_len == 126]
      [8 bytes extended len if payload_len == 127]
      [4 bytes masking key if MASK == 1]
      [payload]
    """
    if len(data) < 2:
        return None, 0

    b0, b1 = data[0], data[1]
    fin    = bool(b0 & 0x80)
    rsv1   = bool(b0 & 0x40)
    rsv2   = bool(b0 & 0x20)
    rsv3   = bool(b0 & 0x10)
    opcode = b0 & 0x0F
    masked = bool(b1 & 0x80)
    plen   = b1 & 0x7F

    offset = 2

    if plen == 126:
        if len(data) < offset + 2:
            return None, 0
        plen = struct.unpack("!H", data[offset:offset + 2])[0]
        offset += 2
    elif plen == 127:
        if len(data) < offset + 8:
            return None, 0
        plen = struct.unpack("!Q", data[offset:offset + 8])[0]
        offset += 8

    mask_key = None
    if masked:
        if len(data) < offset + 4:
            return None, 0
        mask_key = data[offset:offset + 4]
        offset += 4

    if len(data) < offset + plen:
        return None, 0

    payload = data[offset:offset + plen]
    if masked and mask_key:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))

    frame = {
        "fin":     fin,
        "rsv1":    rsv1,
        "rsv2":    rsv2,
        "rsv3":    rsv3,
        "opcode":  opcode,
        "masked":  masked,
        "length":  plen,
        "payload": payload,
    }
    return frame, offset + plen


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def display_frame(frame, direction, src, dst):
    opcode_name = OPCODES.get(frame["opcode"], f"UNKNOWN(0x{frame['opcode']:X})")
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    src_str = f"{src[0]}:{src[1]}"
    dst_str = f"{dst[0]}:{dst[1]}"
    arrow   = "-->" if direction == "client" else "<--"
    clr     = "blue" if direction == "client" else "cyan"

    line = _c(f"[{ts}] {src_str} {arrow} {dst_str} ", clr)
    line += _c(f"[{opcode_name}]", "bold")
    line += _c(f"  {frame['length']} bytes", "dim")
    if frame["masked"]:
        line += _c("  masked", "yellow")
    if not frame["fin"]:
        line += _c("  fragmented", "yellow")
    print(line)

    payload = frame["payload"]
    opcode  = frame["opcode"]

    if opcode == 0x1:  # Text
        try:
            text = payload.decode("utf-8")
            preview = text[:500] + ("…" if len(text) > 500 else "")
            print(f"  {preview}")
        except UnicodeDecodeError:
            print(_c(f"  [invalid UTF-8] {payload[:64].hex()}", "red"))

    elif opcode == 0x2:  # Binary
        hex_str = payload[:32].hex()
        suffix  = "…" if len(payload) > 32 else ""
        print(_c(f"  [binary] {hex_str}{suffix}", "dim"))

    elif opcode == 0x8:  # Close
        if len(payload) >= 2:
            code   = struct.unpack("!H", payload[:2])[0]
            reason = payload[2:].decode("utf-8", errors="replace")
            print(_c(f"  close code={code}  reason={reason!r}", "red"))

    elif opcode in (0x9, 0xA):  # Ping / Pong
        body = payload.hex() if payload else "(empty)"
        print(_c(f"  {body}", "dim"))


# ---------------------------------------------------------------------------
# TCP stream reassembly + WebSocket state machine
# ---------------------------------------------------------------------------

class WsStream:
    """Tracks one bidirectional TCP connection that may carry WebSocket traffic."""

    def __init__(self, client_addr, server_addr):
        self.client_addr = client_addr  # (ip, port) — initiator of HTTP upgrade
        self.server_addr = server_addr
        self.upgraded    = False
        self.bufs        = {True: b"", False: b""}   # True = client->server
        self.frame_count = 0

    def feed(self, data: bytes, from_client: bool):
        self.bufs[from_client] += data

        if not self.upgraded:
            self._detect_upgrade(from_client)
        else:
            self._drain_frames(from_client)

    # --- private ---

    def _detect_upgrade(self, from_client: bool):
        buf = self.bufs[from_client]

        # Server sends "101 Switching Protocols"; client sends "Upgrade: websocket"
        trigger = b"101 Switching Protocols" if not from_client else b"upgrade: websocket"
        if trigger not in buf.lower():
            return

        end = buf.find(b"\r\n\r\n")
        if end == -1:
            return  # headers not fully received yet

        self.upgraded = True
        self.bufs[from_client] = buf[end + 4:]  # keep data after headers

        print(_c(
            f"\n[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}]"
            f"  WebSocket handshake  "
            f"{self.client_addr[0]}:{self.client_addr[1]}"
            f"  <->  "
            f"{self.server_addr[0]}:{self.server_addr[1]}",
            "green", "bold"
        ))

        if self.bufs[from_client]:
            self._drain_frames(from_client)

    def _drain_frames(self, from_client: bool):
        buf = self.bufs[from_client]
        src = self.client_addr if from_client else self.server_addr
        dst = self.server_addr if from_client else self.client_addr
        direction = "client" if from_client else "server"

        while len(buf) >= 2:
            frame, consumed = parse_ws_frame(buf)
            if frame is None:
                break
            buf = buf[consumed:]
            self.frame_count += 1
            display_frame(frame, direction, src, dst)

        self.bufs[from_client] = buf


# ---------------------------------------------------------------------------
# Packet decoder
# ---------------------------------------------------------------------------

class WebSocketDecoder:

    def __init__(self, port=None, interface=None, pcap_file=None):
        self.port      = port
        self.interface = interface
        self.pcap_file = pcap_file
        self.streams   = {}   # canonical 4-tuple -> WsStream

    # --- packet callback ---

    def _process(self, pkt):
        if not (pkt.haslayer(IP) and pkt.haslayer(TCP) and pkt.haslayer(Raw)):
            return

        src_ip   = pkt[IP].src
        dst_ip   = pkt[IP].dst
        src_port = pkt[TCP].sport
        dst_port = pkt[TCP].dport
        data     = bytes(pkt[Raw].load)

        if not data:
            return

        # Canonical key: sort the two endpoints so both directions share one entry
        ep_a = (src_ip, src_port)
        ep_b = (dst_ip, dst_port)
        if ep_a <= ep_b:
            key = (ep_a, ep_b)
            from_client_perspective = True
        else:
            key = (ep_b, ep_a)
            from_client_perspective = False

        if key not in self.streams:
            # Heuristic: the side connecting *to* the watched port is the server
            if self.port and dst_port == self.port:
                client_addr, server_addr = (src_ip, src_port), (dst_ip, dst_port)
            elif self.port and src_port == self.port:
                client_addr, server_addr = (dst_ip, dst_port), (src_ip, src_port)
            else:
                client_addr, server_addr = (src_ip, src_port), (dst_ip, dst_port)
            self.streams[key] = WsStream(client_addr, server_addr)

        stream      = self.streams[key]
        from_client = (src_ip, src_port) == stream.client_addr
        stream.feed(data, from_client)

    # --- public API ---

    def run(self):
        bpf = f"tcp port {self.port}" if self.port else "tcp"

        print(_c("WebSocket Traffic Decoder", "bold", "green"))
        print(_c(f"BPF filter : {bpf}", "dim"))

        if self.pcap_file:
            print(_c(f"Source     : {self.pcap_file}", "dim"))
        else:
            iface = self.interface or "any"
            print(_c(f"Interface  : {iface}", "dim"))

        print(_c("-" * 60, "dim"))

        try:
            if self.pcap_file:
                sniff(offline=self.pcap_file, filter=bpf,
                      prn=self._process, store=False)
            else:
                sniff(iface=self.interface, filter=bpf,
                      prn=self._process, store=False)
        except PermissionError:
            print(_c("Error: permission denied — run with sudo for live capture.", "red"))
            sys.exit(1)
        except KeyboardInterrupt:
            total_frames   = sum(s.frame_count for s in self.streams.values())
            total_streams  = len(self.streams)
            upgraded       = sum(1 for s in self.streams.values() if s.upgraded)
            print(_c(
                f"\n\nStopped.  "
                f"TCP streams seen: {total_streams}  "
                f"WebSocket streams: {upgraded}  "
                f"Frames decoded: {total_frames}",
                "bold"
            ))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Decode WebSocket traffic on Ubuntu",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  sudo python3 websocket_decoder.py                   # all TCP traffic
  sudo python3 websocket_decoder.py -p 8080           # filter by port
  sudo python3 websocket_decoder.py -i eth0 -p 443    # specific interface + port
       python3 websocket_decoder.py -f dump.pcap      # read from pcap file
        """,
    )
    parser.add_argument("-p", "--port",      type=int, help="TCP port to watch (e.g. 80, 8080)")
    parser.add_argument("-i", "--interface",           help="Network interface  (default: any)")
    parser.add_argument("-f", "--file",                help="Read from pcap file instead of live capture")
    args = parser.parse_args()

    WebSocketDecoder(
        port      = args.port,
        interface = args.interface,
        pcap_file = args.file,
    ).run()


if __name__ == "__main__":
    main()
