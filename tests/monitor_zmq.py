# Trying to monitor ZMQ connections and commands
import zmq

# Create a context and socket
context = zmq.Context()
socket = context.socket(zmq.REP)
socket.bind("tcp://*:29160")

# Create a monitor for the socket
monitor_socket = socket.get_monitor_socket()

while True:
    message = monitor_socket.recv_string(flags=zmq.NOBLOCK)
    print("Monitor event:", message)
