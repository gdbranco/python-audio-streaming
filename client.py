'''
Change the ip address to the one on which server file is running
run using command in linux : "python3 client.py"

enter sample to run the sample audio

'''

import socket
import pyaudio
import logging
from _thread import *
import threading
import tqdm
import queue
import time

COMMAND_RESPONSE_SIZE = 1024
RX_TIMEOUT = 2.0
SONG_DATA_END_MESSAGE = "song_data_end"
LEN_SONG_DATA_END_MESSAGE = len(SONG_DATA_END_MESSAGE)

def receive(conn):
	message = ""
	conn.settimeout(RX_TIMEOUT)
	try:
		recvBytes = conn.recv(COMMAND_RESPONSE_SIZE).decode()
		message = str(recvBytes)
		logger.debug(f"Received {message} from {conn}")
		return message
	except Exception as error:
		logger.error(error)
	return ""

def playSong(conn):
	rawMetadata=receive(conn)
	parsedMetadata = parseSongMetadata(rawMetadata)
	print(f" Track '{parsedMetadata['name']}' playing")		
	conn.send("ack".encode())

	stream = p.open(format=p.get_format_from_width(int(parsedMetadata["width"])),
                channels=int(parsedMetadata["channels"]),
                rate=int(parsedMetadata["rate"]),
                output=True)
	tx_chunk = int(parsedMetadata["sec_per_tx"])*int(parsedMetadata["rate"])*int(parsedMetadata["channels"])*int(parsedMetadata["width"])
	data_size = int(parsedMetadata["size"])
	q = queue.Queue(maxsize=data_size)
	def getAudioData():
		conn.settimeout(RX_TIMEOUT)
		done = False
		file_bytes = b""
		logger.info("RX streaming song")
		while not done:
			try:
				logger.debug("RX song")
				data = conn.recv(tx_chunk)
				file_bytes+=data
				if file_bytes[-LEN_SONG_DATA_END_MESSAGE:] == SONG_DATA_END_MESSAGE.encode():
					done = True
					continue
				q.put(data)
			except TimeoutError:
				logger.warning("Timeout Error: server stopped responding song data")
				done = True
				continue
		conn.settimeout(None)
		logger.info("RX all packets for song")
	t1 = threading.Thread(target=getAudioData, args=())
	t1.start()
	time.sleep(RX_TIMEOUT)
	logger.info("Playing received content")
	while not q.empty():
		frame = q.get()
		stream.write(frame)
	logger.info("Finished playing received content")
	stream.stop_stream()
	stream.close()

def parseSongMetadata(songMetadata):
	parsed = {}
	splitSongMetadata = songMetadata.split(";")
	for _metadata in splitSongMetadata:
		splitMetadata = _metadata.split("=")
		logger.debug(splitMetadata)
		parsed[splitMetadata[0]] = splitMetadata[1]
	return parsed

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
conn.connect(("127.0.0.1", 5544))
paused = False

p = pyaudio.PyAudio()
done = False
while not done:
	command=input("Enter command: ")
	splitCommand = command.split(" ")
	logger.info(f"Sending {command} to server")
	conn.send(command.encode())
	resp=receive(conn)
	if not resp:
		continue
	if resp == "song_data_start":
		playSong(conn)
	elif resp.lower() == "goodbye":
		done = True
		conn.close()
		break
	else:
		print(resp)

p.terminate()