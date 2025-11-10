import socket
import threading
import sys
import math
import json
import time 

lock = threading.Lock()

def main():

    global port, packet_count, update_interval, server_id
    packet_count = 0
    server_id = None
    update_interval = None

    global ip_ports
    ip_ports = {}

    global distances
    distances = {}

    global neighbor_edges
    neighbor_edges = {}

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
                build_initial_table(filename)
                # print(server_id)
                thread1 = threading.Thread(target=handle_updates, daemon=True)
                thread1.start()
                thread2 = threading.Thread(target=periodic_step, daemon=True)
                thread2.start()
            elif command == "update":
                dest_id = int(parts[2])
                dest_ip, dest_port = ip_ports[dest_id]
                update(dest_ip, int(dest_port), parts[1:])
            elif command == "step":
                step()
            elif command == "packets":
                print(f"Number of packets: {packet_count}")
                packet_count = 0
            elif command == "display":
                print(distances)
                # TODO implement display()
            elif command == "disable":
                target_id = int(parts[1])
                disable(target_id)
            else:
                print("Bye!")
                sys.exit(0)
                
        except Exception as e:
            print(f"Error: {e}")

def update(dest_ip, dest_port, cost_update):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    dest_id = int(cost_update[1])
    new_cost = cost_update[2]
    if new_cost == "inf":
        new_cost = math.inf
    else:
        new_cost = int(new_cost)

    # print(dest_id)
    # print(new_cost)

    with lock:
        neighbor_edges[dest_id] = new_cost

        if distances[dest_id][0] == dest_id and new_cost > distances[dest_id][1]:
            distances[dest_id] = (dest_id, new_cost)

        str_update = " ".join(cost_update)
        message = {"type": "update", "update": str_update}

        data = json.dumps(message)

        s.sendto(data.encode(), (dest_ip, dest_port))

        s.settimeout(1)

        try:
            data, _ = s.recvfrom(1024)
            reply = data.decode()
            if reply == "Message SUCCESS":
                print(f"Sent update to {dest_id}")
        except socket.timeout:
            print(f"No reply from {dest_id}, update may not have been received")

def periodic_step():
    global update_interval, update_index

    update_index = 1
    while True:
        step()
        to_disable = []
        with lock:
            for neighbor in last_update:
                # print(f"cur update index = {update_index}")
                # print(f"last updated for {neighbor} was {last_update[neighbor]}")
                if last_update[neighbor] + 3 < update_index and neighbor_edges[neighbor] != math.inf:
                    to_disable.append(neighbor)
        for server in to_disable:
            disable(server)
            # print("disabled " + str(server))
        with lock:
            update_index += 1
        # print(distances)
        time.sleep(update_interval)

def step():
    global distances, server_id

    with lock:
        message = {"type": "step", "id": server_id, "distances": distances}
        dv_data = json.dumps(message)

        for neighbor in neighbor_edges:
            # print("neighbor = " + str(neighbor))
            try:
                dest_ip, dest_port = ip_ports[neighbor]
                s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                s.settimeout(1.0)
                s.sendto(dv_data.encode(), (dest_ip, int(dest_port)))
                try:
                    data, _ = s.recvfrom(1024)
                    reply = data.decode()
                    if reply == "Message SUCCESS":
                        print(f"Sent routing table to {neighbor}")
                except Exception as e:
                    continue
            except Exception as e:
                print(f"Error sending to neighbor {neighbor}: {e}")


def handle_updates():
    global port, packet_count
    # server side - create a connection/socket and listen on it
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    # check if we are able to bind to the port
    try:
        s.bind(("", int(port)))
    except OSError as e:
        print(f"Error: Could not bind to port {port}: {e}")
        sys.exit(1)
        return

    while True:
        # use recvfrom in udp socket
        data, address = s.recvfrom(1024)
        # decode the received data to string and print out
        message = json.loads(data.decode())

        print(f"Got message {message}")

        if message["type"] == "update":
            parts = message["update"].split(" ")

            from_server = int(parts[0])
            
            cost = parts[2]
            if cost == "inf":
                cost = math.inf
            else:
                cost = int(parts[2])

            with lock:
                neighbor_edges[from_server] = cost

                if distances[from_server][0] == from_server and cost > distances[from_server][1]:
                    distances[from_server] = (from_server, cost)
                # s.sendto("Message SUCCESS".encode(), address)

            # print(neighbor_edges)
        
        else:
            recv_distances = message["distances"]
            # perform Bellman-Ford
            neighbor_id = message["id"]

            # print("my distances: ")
            # print(distances)

            with lock:
                for server, min_path in recv_distances.items():
                    next_hop, min_cost = min_path
                    server = int(server)
                    # if neighbor link was disabled
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
                        if neighbor_edges[neighbor_id]+min_cost < cur_cost:
                            distances[server] = (neighbor_id, neighbor_edges[neighbor_id]+min_cost)

                last_update[neighbor_id] = update_index

        s.sendto("Message SUCCESS".encode(), address)
        packet_count += 1

    # close server socket
    s.close()

def build_initial_table(filename):
    global port, server_id

    with open(filename, "r") as f:
        num_servers = int(f.readline())
        num_neighbors = int(f.readline())

        for _ in range(num_servers):
            server = f.readline()
            parts = server.strip("\n").split(" ")
            cur_id = int(parts[0])
            cur_ip = parts[1]
            cur_port = int(parts[2])
            ip_ports[cur_id] = (cur_ip, cur_port)
            distances[cur_id] = (None, math.inf)

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

        # print(ip_ports)
        # print(distances)

def disable(target_id):
    
    with lock:
        if target_id not in neighbor_edges:
            print(f"Can not disable because no connection exists to {target_id}")
            return
        neighbor_edges[target_id] = math.inf
        for server in distances:
            min_path = distances[server]
            next_hop, _ = min_path
            if next_hop == target_id:
                distances[server] = (None, math.inf)


if __name__ == "__main__":
    try:
        main()
    # handle keyboard errors/system exceptions
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)