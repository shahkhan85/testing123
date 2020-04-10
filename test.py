import pexpect

fw = pexpect.spawn('ssh -o StrictHostKeyChecking=no admin@172.16.20.2')
fw.expect("sword: ")
fw.sendline('T6NJnz3kp!zK^JFR')
fw.expect("> $")
fw.sendline("set cli scripting-mode on")
fw.expect("> $")
fw.sendline("set cli pager off")
fw.expect("> $")
fw.sendline("show clock")
fw.expect("> $")

output = fw.before
print (output)

fw.sendline("show jobs all")
fw.expect("> $")
output = fw.before
print (output)

fw.sendline("debug user-id dump domain-map")
fw.expect("> $")

output = fw.before
print (output)
