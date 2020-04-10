import pexpect

fw = pexpect.spawn("ssh -o StrictHostKeyChecking=no admin@172.16.20.2")
fw.expect("assword: ")
fw.sendline("T6NJnz3kp!zK^JFR")
fw.expect("> $")
fw.sendline("set cli scripting-mode on")
fw.expect("> $")
fw.sendline("set cli pager off")
fw.expect("> $")
fw.sendline("show clock")
fw.expect("> $")
clock = fw.before
print(clock)
fw.sendline("show user user-ids all")
fw.expect("> $")
userinfo = fw.before
print(userinfo)
fw.sendline("show user group list")
fw.expect("> $")
grouplist= fw.before
print(grouplist)
fw.sendline("show user user-attribute all")
fw.expect("> $")
useratt= fw.before
print(useratt)

