import socket
import threading
import sys
import math
import json
import time 

# lock to ensure thread safe access to variables
lock = threading.Lock()

def main():

    # define global variables for port, packet number, update interval, server id
    global port, packet_count, update_interval, server_id
    packet_count = 0
    server_id = None
    update_interval = None

    # define ip and ports dictionary for all servers in network topology
    global ip_ports
    ip_ports = {}

    # define routing table storing next hop and shortest distance for each server
    global distances
    distances = {}

    # define distance to neighbors dictionary
    global neighbor_edges
    neighbor_edges = {}

    # define dictionary to keep track of last update received from each server 
    global last_update
    last_update = {}

    while True:
        try:
            user_input = input("> ").strip()
            
            if not user_input:
                continue
            
            # split user input into parts
            parts = user_input.split(" ")
            command = parts[0].lower()
            
            # check command user entered
            if command == "server":
                filename = parts[2]
                update_interval = int(parts[4])
                # construct initial table from topology file
                build_initial_table(filename)
                # start two threads, one for receiving DV tables from neighbors and one for sending own table
                thread1 = threading.Thread(target=handle_updates, daemon=True)
                thread1.start()
                thread2 = threading.Thread(target=periodic_step, daemon=True)
                thread2.start()
            elif command == "myip":
                print(get_ip())
            elif command == "update":
                dest_id = int(parts[2])
                dest_ip, dest_port = ip_ports[dest_id]
                update(dest_ip, int(dest_port), parts[1:])
            elif command == "step":
                step()
            elif command == "packets":
                print(f"Number of packets: {packet_count}")
                print("packets SUCCESS")
                packet_count = 0
            elif command == "display":
                display()
                print("display SUCCESS")
            elif command == "disable":
                target_id = int(parts[1])
                disable(target_id)
            elif command == "crash":
                print("Bye!")
                sys.exit(0)
            else:
                print("Unknown command")
                
        except Exception as e:
            print(f"Error: {e}")

def display():
    global distances

    with lock:
        print("dest\t\t\tcost\t\t\tnext hop")
        for server, min_path in distances.items():
            print(f"{server}\t\t\t{min_path[1]}\t\t\t{min_path[0]}")

def get_ip():
    # create a UDP socket for quick, limited-overhead connection to google DNS
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    # connect to google ip
    s.connect(("8.8.8.8", 80))
    # extract the ip address
    ip = s.getsockname()[0]
    s.close()
    return ip

def update(dest_ip, dest_port, cost_update):
    # create UDP socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    dest_id = int(cost_update[1])
    new_cost = cost_update[2]
    # initialize new cost provided by update command
    if new_cost == "inf":
        new_cost = math.inf
    else:
        new_cost = int(new_cost)

    with lock:
        # update distance to neighbor to the new cost
        neighbor_edges[dest_id] = new_cost

        # if current minimum distance to neighbor had next hop neighbor, change routing table to reflect
        if distances[dest_id][0] == dest_id and new_cost > distances[dest_id][1]:
            distances[dest_id] = (dest_id, new_cost)

        # send update as json to destination
        str_update = " ".join(cost_update)
        message = {"type": "update", "update": str_update}

        data = json.dumps(message)

        s.sendto(data.encode(), (dest_ip, dest_port))

        s.settimeout(1)

        # receive reply from destination for success and catch timeout
        try:
            data, _ = s.recvfrom(1024)
            reply = data.decode()
            if reply == "Message SUCCESS":
                print(f"Sent update to {dest_id}")
                print("update SUCCESS\n>", end=' ')
        except socket.timeout:
            print(f"No reply from {dest_id}, update may not have been received\n>", end=' ')

def periodic_step():
    global update_interval, update_index

    # keep track of update iteration index
    update_index = 1
    while True:
        step()
        to_disable = []
        with lock:
            # disable connections to all servers where no update has been received for 3 intervals
            for neighbor in last_update:
                if last_update[neighbor] + 3 < update_index and neighbor_edges[neighbor] != math.inf:
                    to_disable.append(neighbor)
        for server in to_disable:
            disable(server)
        with lock:
            update_index += 1
        # sleep for interval time
        time.sleep(update_interval)

def step():
    global distances, server_id

    with lock:
        # create step message and convert to json
        message = {"type": "step", "id": server_id, "distances": distances}
        dv_data = json.dumps(message)

        for neighbor in neighbor_edges:
            try:
                # send DV table to each neighbor using stored ip and port
                dest_ip, dest_port = ip_ports[neighbor]
                # create UDP socket
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(1.0)
                s.sendto(dv_data.encode(), (dest_ip, int(dest_port)))
                try:
                    data, _ = s.recvfrom(1024)
                    reply = data.decode()
                    if reply == "Message SUCCESS":
                        print(f"Sent routing table to {neighbor}\n>", end=' ')
                except Exception as e:
                    continue
            except Exception as e:
                print(f"Error sending to neighbor {neighbor}: {e}\n>", end=' ')


def handle_updates():
    global port, packet_count
    # server side - create a connection/socket and listen on it
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # check if we are able to bind to the port
    try:
        s.bind(("", int(port)))
    except OSError as e:
        print(f"Error: Could not bind to port {port}: {e}\n>", end=' ')
        sys.exit(1)
        return

    while True:
        # use recvfrom in UDP socket
        data, address = s.recvfrom(1024)
        # decode the received data to string and acknowledge received message
        message = json.loads(data.decode())

        print(f"Got message from {address}\n>", end=' ')

        # check whether update or step type of message
        if message["type"] == "update":
            parts = message["update"].split(" ")

            from_server = int(parts[0])
            
            cost = parts[2]
            if cost == "inf":
                cost = math.inf
            else:
                cost = int(parts[2])

            with lock:
                # set neighbor direct cost to new cost
                neighbor_edges[from_server] = cost

                if distances[from_server][0] == from_server and cost > distances[from_server][1]:
                    distances[from_server] = (from_server, cost)
        
        else:

            # retrieve distances from message and perform Bellman-Ford algorithm to update own DV table
            recv_distances = message["distances"]
            neighbor_id = message["id"]

            with lock:
                for server, min_path in recv_distances.items():
                    next_hop, min_cost = min_path
                    server = int(server)
                    # if neighbor link was disabled, update to infinity
                    if server == server_id and next_hop is None:
                        neighbor_edges[neighbor_id] = math.inf
                        distances[neighbor_id] = (None, math.inf)
                        continue
                    # avoid infinite loops of next hop being current server
                    if next_hop == server_id:
                        continue
                    # if a previous path is now more expensive (with same next hop), must update
                    new_distance = neighbor_edges[neighbor_id]+min_cost
                    if server in distances and new_distance > distances[server][1] and distances[server][0] == neighbor_id:
                        if next_hop is None or new_distance is math.inf:
                            distances[server] = (None, math.inf)
                        else:
                            distances[server] = (neighbor_id, new_distance)
                        continue
                    if server not in distances:
                        distances[server] = (neighbor_id, min_cost)
                    else:
                        _, cur_cost = distances[server]
                        # if found less expensive path, perform update to routing table with new next hop and cost
                        if neighbor_edges[neighbor_id]+min_cost < cur_cost:
                            distances[server] = (neighbor_id, neighbor_edges[neighbor_id]+min_cost)

                last_update[neighbor_id] = update_index

        s.sendto("Message SUCCESS".encode(), address)
        packet_count += 1

    # close server socket
    s.close()

def build_initial_table(filename):
    global port, server_id

    # open file and save ip, port of all servers and initialize distances and neighbor_edges
    with open(filename, "r") as f:
        num_servers = int(f.readline())
        num_neighbors = int(f.readline())

        # store ip, port values
        for _ in range(num_servers):
            server = f.readline()
            parts = server.strip("\n").split(" ")
            cur_id = int(parts[0])
            cur_ip = parts[1]
            cur_port = int(parts[2])
            ip_ports[cur_id] = (cur_ip, cur_port)
            distances[cur_id] = (None, math.inf)

        # store neighbor costs
        for _ in range(num_neighbors):
            connection = f.readline()
            parts = connection.split(" ")
            server_id = int(parts[0])
            neighbor = int(parts[1])
            cost = int(parts[2])
            distances[neighbor] = (neighbor, cost)
            neighbor_edges[neighbor] = cost
            last_update[neighbor] = 0

        distances[server_id] = (server_id, 0)
        _, port = ip_ports[server_id]

def disable(target_id):
    
    with lock:
        if target_id not in neighbor_edges:
            print(f"Can not disable because no connection exists to {target_id}\n>", end=' ')
            return
        # set distance to target neighbor to infinity 
        neighbor_edges[target_id] = math.inf
        # set all distances that have next hop as target to infinity
        for server in distances:
            min_path = distances[server]
            next_hop, _ = min_path
            if next_hop == target_id:
                distances[server] = (None, math.inf)
    
    print("disable SUCCESS\n>", end=' ')


if __name__ == "__main__":
    try:
        main()
    # handle keyboard errors/system exceptions
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)