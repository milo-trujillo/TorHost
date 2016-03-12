#!/usr/bin/env python

import sys, signal, socket, time, os.path, stem.process, argparse
from stem.control import Controller
from stem.util import term
from thread import *

#
# These are global constants, to be read but not set anywhere
#
"""
	It appears that Tor does some kind of buffering and isn't completely in sync
	with the sockets we have open. Specifically if we send data to a client and
	then immediately kill Tor the data will still be inside Tor's buffers and
	fail to send. I've only been able to reproduce the problem with keep-alive
	mode turned off, so the delay is pretty small. Pausing a couple seconds
	before killing Tor seems to solve the issue entirely.
"""
DelayTorExit = 2 # Delay is in seconds
DefaultServicePort = 80
ChunkSize = 1000 # How many bytes to read from a file at a time

#
# These are global options, and are set by command line arguments
#
ServicePort = DefaultServicePort
KeepAlive = False
DebugMode = False
FileName = ""

# Signal handler for Control-C
def sigExit(signal, frame):
	print("") # Send newline in platform-agnostic way
	print("Waiting for Tor to clean up before exiting...")
	time.sleep(DelayTorExit)
	sys.exit(0)

# This creates a socket and binds it for listening on a random port
# returns (socket, port-number)
def getSocket():
	sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	try:
		sock.bind(('', 0)) # Port 0 lets the OS choose a random port for us
		sock.listen(10) # Set as server socket
		return (sock, sock.getsockname()[1])
	except socket.error as msg:
		print(term.format("Unable to bind to any port! Error: " + msg[1], term.Color.RED))
		sys.exit(1)

# Creates an ephemeral hidden service, connects it to the locally bound socket,
# and begins hosting the file
def startHiddenService(localPort, controlPort, filename, sock):
	print "Starting hidden service (this may take a while) ..."
	with Controller.from_port(port = controlPort) as ctrl:
		ctrl.authenticate()
		state = ctrl.create_ephemeral_hidden_service({ServicePort: localPort}, await_publication = True, detached = True)
		onion = "Service available at " + str(state.service_id) + ".onion"
		if( ServicePort != DefaultServicePort ):
			onion = onion + " (port " + str(ServicePort) + ")"
		print(term.format(onion, term.Color.GREEN))
		hostFile(filename, sock)
		# Note: We must pause *here*, if we leave the 'with Controller' section
		# the hidden service is destroyed before we can finish the transfer!
		print("Waiting for Tor to clean up before exiting...")
		time.sleep(DelayTorExit)

# Sends the file once, to a single client
# If you want multiple clients, run this function in a loop with threads
def uploadFile(filename, client):
	try:
		print(term.format(("Uploading file '%s' to new client" % filename), 
		      term.Color.YELLOW))
		f = open(filename, "rb")
		while( True ):
			data = f.read(ChunkSize)
			if( len(data) == 0 ):
				debugMsg("Done reading file")
				break # We've hit EOF
			client.sendall(data)
		f.close()
		client.close()
		print(term.format("File upload complete", term.Color.YELLOW))
	except:
		print(term.format("Unexpected error: " + str(sys.exc_info()[0]), 
		      term.Color.RED))

# This calls uploadFile, either once or as needed, depending on KeepAlive
def hostFile(filename, sock):
	if( KeepAlive == True ):
		print("Keepalive mode is enabled, so press CTRL-C to end the program")
		while(True):
			client, addr = sock.accept()
			debugMsg("New client: " + addr[0])
			start_new_thread(uploadFile, (filename, client,))
	else:
		client, addr = sock.accept()
		debugMsg("New client: " + addr[0])
		uploadFile(filename, client)

# Colorful bootstrap, skips the date and "[notice]" parts of the lines
def bootstrapTor(line):
	pos = line.find("Bootstrapped ")
	if( pos != -1 ):
		print(term.format(line[pos:], term.Color.BLUE))
	elif( DebugMode ):
		pos = line.find('[')
		if( pos != -1 ):
			debugMsg(term.format(line[pos:], term.Color.CYAN))
		else:
			debugMsg("Unexpected Tor bootstap line: " + line)

# Start daemon with a random control port, returning a Tor process and port num
def startTor():
	"""
	We want a random un-used port for Tor control. It needs to be random so we
	can run alongside other TorHost instances or normal Tor instances without
	interfering with them. The easiest way to get a random port seems to be to
	let the system pick a random port by binding a socket, unbinding the port, 
	then immediately starting Tor using the now-free port.
	"""
	(sock, port) = getSocket()
	sock.close
	debugMsg("Found random control port: " + str(port))
	tor = stem.process.launch_tor_with_config(
		config = {
			'ControlPort': str(port),
			# We should probably also generate a random password and use it for
			# authentication, but that is a task for another day.
		},
		init_msg_handler = bootstrapTor,
		take_ownership = True,
	)
	return (tor, port)

# This is a wrapper so I don't have debug if-statements everywhere
def debugMsg(msg):
	if( DebugMode == True ):
		print msg

"""
	Warn the user if the file they've asked us to host doesn't exist or isn't
	accessible. This is a warning, not an error, because we don't actually need
	the file until a client connects. So long as the file exists and is readable
	by that point then we're all good.
"""
def verifyFile(filename):
	if( os.path.isfile(filename) and os.access(filename, os.R_OK) ):
		return
	print(term.format("WARNING: File '" + filename + "' does not exist or is "
		"not readable!", 
		term.Color.MAGENTA))

# We needed to change the behavior of ArgumentParser to print full usage
# information if the user doesn't specify a file to upload.
class Parser(argparse.ArgumentParser):
	def error(self, message):
		sys.stderr.write('error: %s\n' % message)
		self.print_help()
		sys.exit(2)

# Verifies command line arguments and flags, sets global variables accordingly
def parseOptions():
	# This should be the only function with write permission to global settings
	global ServicePort
	global KeepAlive
	global DebugMode
	global FileName
	descr = "Easily and anonymously host files over Tor."
	parser = Parser(description=descr)
	parser.add_argument("-p", "--port", 
	                  action="store", type=int, dest="port", default=80,
	                  metavar="PORT",
	                  help="Specify port to host hidden service on ")
	parser.add_argument("-k", "--keepalive", 
	                  action="store_true", dest="keepalive", default=False,
	                  help="Upload file to multiple users instead of one")
	parser.add_argument("-d", "--debug", 
	                  action="store_true", dest="debug", default=False,
	                  help="Enable debugging information")
	parser.add_argument('file', metavar='<file>', nargs=1,
	                  help='file to upload')
	options = parser.parse_args()
	# At this point all our options are set in options.foo
	if( options.port < 1 ):
		print("Impossible to bind to desired port!")
		parser.print_help()
		sys.exit(1)
	ServicePort = options.port
	KeepAlive = options.keepalive
	DebugMode = options.debug
	FileName = options.file[0]
	debugMsg("=== TorHost Configuration ===")
	debugMsg("Service port: " + str(ServicePort))
	debugMsg("KeepAlive: " + str(KeepAlive))
	debugMsg("DebugMode: " + str(DebugMode))
	debugMsg("FileName: " + str(FileName))

if __name__ == '__main__':
	parseOptions()                        # Validate and interpret arguments
	verifyFile(FileName)                  # Make sure file exists / is readable
	signal.signal(signal.SIGINT, sigExit) # Register signal handler
	(sock, localPort) = getSocket()       # Bind to a socket for hosting files
	debugMsg("Hosting on local port: " + str(localPort))
	print("Starting Tor...")
	(tor, controlPort) = startTor()       # Start the Tor daemon
	startHiddenService(localPort, controlPort, FileName, sock) # Host with Tor
	tor.kill() # Kill the daemon cleanly if we get to this point
