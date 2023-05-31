import socket
import wave
import os
import threading
import logging
import signal

COMMAND_RESPONSE_SIZE = 1024
SECONDS_PER_TX = 5
ACK_TIMEOUT = 2.0
BUFF_SIZE = 65536

# Based on https://stackoverflow.com/questions/18499497/how-to-process-sigterm-signal-gracefully
class GracefulKiller:
  kill_now = False
  def __init__(self):
    signal.signal(signal.SIGINT, self.exit_gracefully)
    signal.signal(signal.SIGTERM, self.exit_gracefully)

  def exit_gracefully(self, *args):
    self.kill_now = True
    

def sendTrackList(conn):
	resource=os.listdir("./resources")
	ss = ""
	for i in range(len(resource)-1):
			ss+=f"{resource[i][:-4]}\n"
	ss += f"{resource[-1][:-4]}"
	send(conn, ss.encode())

def checkTrackExists(track):
	resource=os.listdir("./resources")
	logger.debug(f"os list dir {resource}")
	for i in resource:
		if i.lower().startswith(track.lower()):
			return True, i
	return False, ""

def send(conn: socket, message: bytes):
	logger.debug(f"Sending message {str(message)} to {conn}")
	conn.send(message)

def waitAck(conn):
	conn.settimeout(ACK_TIMEOUT)
	done = False
	data = ""
	while not done:	
		logger.debug(f"Waiting ack from {conn}")
		try:
			data=str(conn.recv(COMMAND_RESPONSE_SIZE).decode())
			if not data:
				continue
		except ConnectionResetError:
			conn.settimeout(None)
			raise(ConnectionResetError)
		except TimeoutError:
			conn.settimeout(None)
			raise(TimeoutError)
		if data == "ack":
			logger.debug(f"Received ack from {conn}")
			done = True
			continue
	conn.settimeout(None)

def downloadTrack(name, conn):
	fileName=f"./resources/{name}"
	logger.info(f"Playing {fileName}")

	wf = wave.open(fileName, 'rb')
	fileStats = os.stat(fileName)

	chunk = SECONDS_PER_TX*wf.getframerate()*wf.getnchannels()
	logger.debug(chunk)
	send(conn,b"track_data_start")
	send(conn, f"sec_per_tx={SECONDS_PER_TX};width={wf.getsampwidth()};name={name[:-4]};size={fileStats.st_size};rate={wf.getframerate()};channels={wf.getnchannels()}".encode())
	try:
		waitAck(conn)
	except ConnectionResetError:
		raise(ConnectionResetError)
	except TimeoutError:
		raise(TimeoutError)
	trackData = " "
	while len(trackData):
		trackData = wf.readframes(chunk)
		logger.debug(f"Sending {SECONDS_PER_TX} seconds of track {fileName}")
		conn.send(trackData)
	send(conn, "track_data_end".encode())
	logger.info(f"Finished sending {fileName}")

def clientthread(conn,address):
	logger.info(f"<{address}> connected")
	done = False
	while not done:
		try:
			data=str(conn.recv(COMMAND_RESPONSE_SIZE).decode())
			if not data:
				raise(ConnectionResetError)
			logger.info(f"from connected {address}: {data}")
			splitData = data.split(" ")
			if splitData[0] == "list":
				sendTrackList(conn)
			elif splitData[0] in ["exit", "quit"]:
				done = True
				send(conn, f"Goodbye".encode())
				conn.close()
				continue
			elif splitData[0] == "download":
				exists, name = checkTrackExists(splitData[1])
				if not exists:
					send(conn, f"Track '{splitData[1]}' not found. Please send 'list' to see track list".encode())
					continue
				try:
					downloadTrack(name, conn)
				except ConnectionResetError:
					logger.warning(f"Connection was reset {address}")
					done = True
					conn.close()
					continue
				except TimeoutError:
					logger.warning(f"Timeout Error, clossing connection to {address}")
					done = True
					conn.close()
					continue
			else:
				send(conn, "Undefined command. Send 'help' for a list of commands".encode())
		except ConnectionResetError:
			logger.warning(f"Connection was reset {address}")
			done = True
			conn.close()
			break
	return
		

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

if __name__ == '__main__':
	killer = GracefulKiller()
	server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, BUFF_SIZE)
	# To allow connecting through internet please port map 5544 as inbound allowed
	server_socket.bind(("0.0.0.0", 5544))
	server_socket.settimeout(0.2)
	server_socket.listen(10)
	while not killer.kill_now:
		try:
			conn, address = server_socket.accept()
		except socket.timeout:
			continue
		logger.info(f"starting client thread for client {address}")
		t=threading.Thread(target=clientthread,args=(conn,address),daemon=True)
		t.start()