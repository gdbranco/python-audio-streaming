'''
store all file to play in the "resource" sub directory where the server file exists
run using command in linux : "python3 server.py"
the audio should be of .wav format with 44100 Hz frequency
'''

import socket
import wave
import os
from _thread import *
import logging
import sys

COMMAND_RESPONSE_SIZE = 1024
SECONDS_PER_TX = 5
ACK_TIMEOUT = 2.0
BUFF_SIZE = 65536

def sendSongList(conn):
	resource=os.listdir("./resources")
	ss = ""
	for i in range(len(resource)-1):
			ss+=f"{resource[i][:-4]}\n"
	ss += f"{resource[-1][:-4]}"
	send(conn, ss.encode())

def sendAvailableCommands(conn):
	send(conn, "[help, list, play <song_name>, exit]".encode())

def checkSongExists(song):
	resource=os.listdir("./resources")
	for i in resource:
		if i.lower().startswith(song.lower()):
			return True, i
		else:
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

def playSong(name, conn):
	fileName=f"./resources/{name}"
	logger.info(f"Playing {fileName}")

	wf = wave.open(fileName, 'rb')
	fileStats = os.stat(fileName)

	chunk = SECONDS_PER_TX*wf.getframerate()*wf.getnchannels()
	logger.debug(chunk)
	send(conn,b"song_data_start")
	send(conn, f"sec_per_tx={SECONDS_PER_TX};width={wf.getsampwidth()};name={name[:-4]};size={fileStats.st_size};rate={wf.getframerate()};channels={wf.getnchannels()}".encode())
	try:
		waitAck(conn)
	except ConnectionResetError:
		raise(ConnectionResetError)
	except TimeoutError:
		raise(TimeoutError)
	songData = " "
	while len(songData):
		songData = wf.readframes(chunk)
		logger.debug(f"Sending {SECONDS_PER_TX} seconds of song {fileName}")
		conn.send(songData)
	send(conn, "song_data_end".encode())
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
				sendSongList(conn)
			elif splitData[0] in ["exit", "quit"]:
				done = True
				send(conn, f"Goodbye".encode())
				conn.close()
				continue
			elif splitData[0] == "play":
				exists, name = checkSongExists(splitData[1])
				if exists:
					try:
						playSong(name, conn)
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
					send(conn, f"Song {splitData[1]} not found. Please send 'list' to see song list".encode())
			elif splitData[0] == "help":
				sendAvailableCommands(conn)
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

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, BUFF_SIZE)
server_socket.bind(("", 5544))
server_socket.listen(10)
done = False
while not done:
	try:
		conn, address = server_socket.accept()
		logger.info(f"starting client thread for client {address}")
		start_new_thread(clientthread,(conn,address))
	except KeyboardInterrupt:
		done = False
		break
	except:
		continue