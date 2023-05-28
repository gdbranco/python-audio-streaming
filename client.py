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
import time
from threading import Lock

COMMAND_RESPONSE_SIZE = 1024
RX_TIMEOUT = 2.0
SONG_DATA_END_MESSAGE = "track_data_end"
LEN_SONG_DATA_END_MESSAGE = len(SONG_DATA_END_MESSAGE)
BUFF_SIZE = 65536
REFRESH_SONG_LIST_CACHE = 30

class ThreadSafeList():
    def __init__(self):
        self._list = list()
        self._lock = Lock()
 
    def append(self, value):
        with self._lock:
            self._list.append(value)
 
    def pop(self):
        with self._lock:
            return self._list.pop()
 
    def get(self, index):
        with self._lock:
            return self._list[index]
 
    def length(self):
        with self._lock:
            return len(self._list)

def send(conn, message: str):
	logger.debug(f"Sending message '{str(message)}' to {conn}")
	conn.send(message.encode())

def receive(conn):
	message = ""
	conn.settimeout(RX_TIMEOUT)
	try:
		recvBytes = conn.recv(COMMAND_RESPONSE_SIZE).decode()
		message = str(recvBytes)
		logger.debug(f"Received '{message}' from {conn}")
		return message
	except Exception as error:
		logger.error(error)
	return ""

def downloadTrack(parsedMetadata: dict):
	# TODO Add a timeout
	# TODO If for some reason the whole track is not downloaded check where we stopped to continue from there
	trackSlice = ThreadSafeList()
	done = False
	logger.info("RX streaming track")
	file_bytes = b""
	tx_chunk = int(parsedMetadata["sec_per_tx"])*int(parsedMetadata["rate"])*int(parsedMetadata["channels"])*int(parsedMetadata["width"])
	while not done:
		logger.debug("RX track")
		data = conn.recv(tx_chunk)
		trackSlice.append(data)
		file_bytes+=data
		if file_bytes[-LEN_SONG_DATA_END_MESSAGE:] == SONG_DATA_END_MESSAGE.encode():
			done = True
			continue
	logger.info("RX all packets for track")
	cachedTracks[str(parsedMetadata['name']).lower()]=(parsedMetadata, trackSlice)

def loadTrack(conn, trackName: str):
	send(conn, f"download {trackName}")
	resp = receive(conn)
	if resp != "track_data_start":
		return
	rawMetadata=receive(conn)
	parsedMetadata = parseTrackMetadata(rawMetadata)	
	conn.send("ack".encode())
	t1 = threading.Thread(target=downloadTrack, args=(parsedMetadata,), daemon=True)
	t1.start()

def playTrack(trackName: str):
	global replay
	global playing_lock
	global playing
	global loop
	with playing_lock:
		playing = True
	trackTuple = cachedTracks[trackName.lower()]
	parsedMetadata = trackTuple[0]
	trackSlice = trackTuple[1]
	stream = p.open(format=p.get_format_from_width(int(parsedMetadata["width"])),
				channels=int(parsedMetadata["channels"]),
				rate=int(parsedMetadata["rate"]),
				output=True)
	logger.info("Playing content")
	done = False
	i=0
	file_bytes = b""
	while not done:
		try:
			if replay:
				replay = False
				i = 0
				continue
			if not playing:
				break
			if paused:
				continue
			frame = trackSlice.get(i)
			file_bytes+=frame
			if file_bytes[-LEN_SONG_DATA_END_MESSAGE:] == SONG_DATA_END_MESSAGE.encode():
				if loop:
					file_bytes = b""
					i = 0
					continue
				done = True
				continue
			i+=1
			stream.write(frame)
		except Exception as err:
			logger.error(err)
	logger.info("Finished playing content")
	with playing_lock:
		playing = False
	stream.stop_stream()
	stream.close()

def parseTrackMetadata(trackMetadata):
	parsed = {}
	splitTrackMetadata = trackMetadata.split(";")
	for _metadata in splitTrackMetadata:
		splitMetadata = _metadata.split("=")
		logger.debug(splitMetadata)
		parsed[splitMetadata[0]] = splitMetadata[1]
	return parsed

def parseTrackList(trackList: str):
	return trackList.lower().split('\n')

def getTrackList(conn):
	global cachedTrackList
	newTime = time.time()
	oldTime = cachedTrackList[1]
	if oldTime == None or (oldTime - newTime) >= REFRESH_SONG_LIST_CACHE:
		send(conn, 'list')
		trackList=receive(conn)
		cachedTrackList = (parseTrackList(trackList), newTime)

logger = logging.getLogger()
#logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
#ch.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s;%(levelname)s;%(message)s")
ch.setFormatter(formatter)
logger.addHandler(ch)

conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
conn.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, BUFF_SIZE)
conn.connect(("127.0.0.1", 5544))
# TODO stop using global vars
paused = False
p = pyaudio.PyAudio()
cachedTrackList = ([], None)
cachedTracks = {}
playing = False
playing_lock = Lock()
loop = False
replay = False

if __name__ == "__main__":
	done = False
	while not done:
		command=input("Enter command: ")
		splitCommand = command.split(" ")
		mainCommand = splitCommand[0].lower()
		try:
			subcommand = splitCommand[1].lower()
		except IndexError:
			logger.debug(f"Index error when splitting command {command} on ' '")
			pass
		if mainCommand == "pause":
			if playing:
				logger.info("Setting paused")
				paused = True
		elif mainCommand == "resume":
			if playing:
				logger.info("Setting resume")
				paused = False
		elif mainCommand in ["restart", "replay"]:
			replay = True
		elif mainCommand == "stop":
			# TODO use a playing state for a specific thread
			with playing_lock:
				if playing:
					playing = False
			if paused:
				paused = False
		elif mainCommand == "loop":
			loop = not loop
			print(f"Loop: {loop}")
		elif mainCommand == "play":
			with playing_lock:
				if playing:
					playing = False
					time.sleep(RX_TIMEOUT*1.5)
			if cachedTrackList[0] == []:
				getTrackList(conn)
			if subcommand not in cachedTrackList[0]:
				print(f"Track '{subcommand}' not found. Please send 'list' to see track list")
				continue
			if not subcommand in cachedTracks:
				print(f"Loading track '{subcommand}'")
				loadTrack(conn, subcommand)
			print(f"Playing track '{subcommand}'")
			time.sleep(RX_TIMEOUT)
			t=threading.Thread(target=playTrack, args=(subcommand,), daemon=True)
			t.start()
		elif mainCommand == "list":
			getTrackList(conn)
			for i in cachedTrackList[0]:
				print(i)
		else:
			logger.info(f"Sending {command} to server")
			send(conn, command)
			resp=receive(conn)
			if not resp:
				continue
			elif resp.lower() == "goodbye":
				done = True
				conn.close()
				break
			else:
				print(resp)

conn.close()
p.terminate()