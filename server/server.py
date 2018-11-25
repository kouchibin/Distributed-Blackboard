# coding=utf-8
# ------------------------------------------------------------------------------------------------------
# TDA596 - Lab 1
# server/server.py
# Input: Node_ID total_number_of_ID
# ------------------------------------------------------------------------------------------------------
import traceback
import sys
import time
import json
import random
import argparse
from threading import Thread
from threading import Lock

from bottle import Bottle, run, request, template, response
import requests
# ------------------------------------------------------------------------------------------------------
try:
    app = Bottle()

    board = {}

    lock = Lock()

    # The sequence number used by the leader for new entries
    current_sequence_number = 0

    # The random number the leader has
    leader_random_number = None
    # The random number the vessel itself has, used for the leader election
    self_random_number = None
    # IP address of the leader
    leader_ip = None

    # Id for next vessel. This field in every vessel constructs a logical ring.
    next_id = None

    # Next vessel id generator
    next_id_generator = None

    # Messages waiting to be ackowledged.
    # This is used for presevering massages when the leader is down and new leader is yet to be elected.
    # The key of the item is the hash value of the value field, i.e., key = hash(value).
    waiting_ack = {}

    # Generate next vessel's id. This method will loop through the vessels ring
    # when called multiple times.
    def get_next_vessel_id():
        global node_id, n_nodes
        next_vessel = node_id + 1
        if next_vessel == n_nodes:
            next_vessel = 1
        yield next_vessel
        while True:
            # Will reach here only when this method is called the second time,
            # which means something wrong with the last generated vessel and
            # we need to jump over the faulty one.
            next_vessel += 1
            if next_vessel == n_nodes:
                next_vessel = 1
            yield next_vessel

    # Return True if I am the leader.
    def is_leader():
        global leader_random_number, self_random_number
        return leader_random_number == self_random_number

    # Returns the leader IP
    def get_leader_ip():
        global leader_ip
        return leader_ip

    # Return True if a leader has been elected.
    def leader_elected():
        global leader_ip
        if leader_ip is not None:
            return True
        else:
            return False

    # ------------------------------------------------------------------------------------------------------
    # BOARD FUNCTIONS
    # Should nopt be given to the student
    # ------------------------------------------------------------------------------------------------------
    def add_new_element_to_store(entry_sequence, element, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            board[entry_sequence] = element
            success = True
        except Exception as e:
            print e
        return success

    def modify_element_in_store(entry_sequence, modified_element, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            board[entry_sequence] = modified_element
            success = True
        except Exception as e:
            print e
        return success

    def delete_element_from_store(entry_sequence, is_propagated_call=False):
        global board, node_id
        success = False
        try:
            # Delete the entry only if it's already there
            if entry_sequence in board:
                del board[entry_sequence]
            success = True
        except Exception as e:
            print e
        return success

    # ------------------------------------------------------------------------------------------------------
    # DISTRIBUTED COMMUNICATIONS FUNCTIONS
    # should be given to the students?
    # ------------------------------------------------------------------------------------------------------
    def contact_vessel(vessel_ip, path, payload=None, req='POST'):
        # Try to contact another server (vessel) through a POST or GET, once
        success = False
        try:
            if 'POST' in req:
                res = requests.post('http://{}{}'.format(vessel_ip, path), data=payload)
            elif 'GET' in req:
                res = requests.get('http://{}{}'.format(vessel_ip, path))
            else:
                print 'Non implemented feature!'
            # result is in res.text or res.json()
            print(res.text)
            if res.status_code == 200:
                success = True
        except Exception as e:
            print e
        return success

    def propagate_to_vessels(path, payload=None, req='POST'):
        global vessel_list, node_id

        for vessel_id, vessel_ip in vessel_list.items():
            if int(vessel_id) != node_id:  # don't propagate to yourself
                success = contact_vessel(vessel_ip, path, payload, req)
                if not success:
                    print "\n\nCould not contact vessel {}\n\n".format(vessel_id)

    # ------------------------------------------------------------------------------------------------------
    # ROUTES
    # ------------------------------------------------------------------------------------------------------
    # a single example (index) should be done for get, and one for post
    # ------------------------------------------------------------------------------------------------------
    @app.route('/')
    def index():
        global board, node_id, leader_ip
        return template('server/index.tpl',
                        board_title='Vessel {}'.format(node_id),
                        board_dict=sorted(board.iteritems()),
                        members_name_string='Oskar Lundström and Kou Chibin',
                        leader_ip=str(leader_ip),
                        leader_random_number=str(leader_random_number))

    @app.get('/board')
    def get_board():
        global board, node_id
        print board
        return template('server/boardcontents_template.tpl',
                        board_title='Vessel {}'.format(node_id),
                        board_dict=sorted(board.iteritems()))
    # ------------------------------------------------------------------------------------------------------

    @app.post('/board')
    def client_add_received():
        '''Adds a new element to the board
           Called directly when a user is doing a POST request on /board
        '''
        global board, node_id, current_sequence_number, waiting_ack
        try:
            # Get the new entry and prepare payload for propagation
            new_entry = request.forms.get('entry')
            message = ('add', -1, new_entry)
            ack_key = hash(message)
            payload = {'entry': new_entry, 'ack_key': ack_key}

            if is_leader():
                # Only the leader adds the element directly to its store
                add_new_element_to_store(current_sequence_number, new_entry)
                # Then it propagates it to all other vessels
                propagate_to_vessels_bg('/prop_to_non_leader/add/' + str(current_sequence_number), payload)
                current_sequence_number += 1
            else:
                # Put the message into the waiting_ack
                waiting_ack[ack_key] = message

                # Notify the leader that we got a new entry
                # The element id is -1, since it should not be used
                contact_leader_bg('/prop_to_leader/add/-1', payload)

            return None
        except Exception as e:
            print e
        return False

    @app.post('/board/<element_id:int>/')
    def client_action_received(element_id):
        global board, waiting_ack
        action = int(request.forms.get('delete'))
        try:
            # Just as for the add, only the leader should do the actual
            # operation directly on its board variable
            if is_leader():
                # Modify entry and propagate
                if action == 0:
                    new_entry = request.forms.get('entry')
                    modify_element_in_store(element_id, new_entry)
                    payload = {'entry': new_entry}
                    # Propagate the modification to the other vessels
                    propagate_to_vessels_bg('/prop_to_non_leader/modify/' + str(element_id), payload)
                # Delete entry and propagate
                elif action == 1:
                    delete_element_from_store(element_id)
                    # Propagate the deletion to the other vessels
                    propagate_to_vessels_bg('/prop_to_non_leader/delete/' + str(element_id))
                else:
                    print 'UNSUPPORTED ACTION!!!'

            # Non-leader
            else:
                # Modify
                if action == 0:
                    new_entry = request.forms.get('entry')
                    message = ('modify', element_id, new_entry)
                    ack_key = hash(message)
                    waiting_ack[ack_key] = message
                    payload = {'entry': new_entry, 'ack_key': ack_key}
                    # Tell the leader we got a modification
                    contact_leader_bg('/prop_to_leader/modify/' + str(element_id), payload)
                # Delete
                elif action == 1:
                    message = ('delete', element_id, None)
                    ack_key = hash(message)
                    waiting_ack[ack_key] = message
                    payload = {'entry': None, 'ack_key': ack_key}
                    # Tell the leader we got a deletion
                    contact_leader_bg('/prop_to_leader/delete/' + str(element_id), payload)
                else:
                    print "UNSUPPORTED ACTION!!!"

            return None
        except Exception as e:
            print e
        return False

    # Helper functions for background contact
    # -------------------------------------------------------------------

    # Same as without _bg, but does it on a background thread
    def propagate_to_vessels_bg(path, payload=None, req='POST'):
        thread = Thread(target=propagate_to_vessels, args=(path, payload, req))
        thread.daemon = True
        thread.start()

    # Contacts the leader in the background
    def contact_leader_bg(path, payload=None, req='POST'):
        # If this times out, start new election
        thread = Thread(target=contact_vessel, args=(get_leader_ip(), path, payload, req))
        thread.daemon = True
        thread.start()

    # Propagations to leader and non-leader
    # ---------------------------------------------------------------

    # A post, which a non-leader sends to the leader whenever
    # an add/modify/delete happens. The leader will then
    # adjust its store, and then notify the non-leaders
    # what happened
    # Note: we assume this function won't be run concurrently
    # since the web server is single-threaded
    @app.post('/prop_to_leader/<action>/<element_id:int>')
    def prop_to_leader_received(action, element_id):
        global current_sequence_number, waiting_ack
        if not is_leader():
            print "Warning, non-leader received propagation intended for leader only."
            return False

        try:
            entry = request.forms.get('entry')
            ack_key = int(request.forms.get('ack_key'))
            payload = {'entry': entry, 'ack_key': ack_key}
            if ack_key in waiting_ack:
                del waiting_ack[ack_key]
            if action == 'add':
                # The leader adds the new entry that it got from a non-leader
                add_new_element_to_store(current_sequence_number, entry)
                # The propagation to non-leaders
                propagate_to_vessels_bg('/prop_to_non_leader/add/' + str(current_sequence_number), payload)
                current_sequence_number += 1
                return None
            elif action == 'modify':
                modify_element_in_store(element_id, entry)
                # The propagation to non-leaders
                propagate_to_vessels_bg('/prop_to_non_leader/modify/' + str(element_id), payload)
                return None
            elif action == 'delete':
                delete_element_from_store(element_id)
                # The propagation to non-leaders
                propagate_to_vessels_bg('/prop_to_non_leader/delete/' + str(element_id), payload)
                return None
            else:
                print "Unsupported action!"
                return False
        except:
            import traceback
            traceback.print_exc()
            return False
        # Note: If the same entry (number) is modified concurrently at
        # different vessels, the last the leader notices is the
        # one that "counts". Not ideal, but at least consistent.
        # A similar behavior happens for a deletion/modifiction combo.

    # The POST that non-leaders get when the leader has modified
    # its store. Now the non-leaders do the actual modification
    # of their stores.
    @app.post('/prop_to_non_leader/<action>/<element_id:int>')
    def prop_to_non_leader_received(action, element_id):
        global waiting_ack, board, current_sequence_number
        try:
            if is_leader():
                print "Warning, leader got propagation intended for non-leaders only"
                return False

            entry = request.forms.get('entry')
            ack_key = request.forms.get('ack_key')
            if ack_key is not None:
                ack_key = int(ack_key)

            # Remove message that is acknowledged from waiting_ack.
            if ack_key in waiting_ack:
                del waiting_ack[ack_key]

            if action == 'add':
                add_new_element_to_store(element_id, entry)
                current_sequence_number = element_id + 1
                return None
            elif action == 'modify':
                modify_element_in_store(element_id, entry)
                return None
            elif action == 'delete':
                delete_element_from_store(element_id)
                return None
            else:
                print "Unsupported action!"
                return False
        except:
            import traceback
            traceback.print_exc()
            return False

    # Leader election
    # --------------------------------------------------------

    # Handle functionalities for leader election.
    # For <action>:
    # 'advertise' - Leader advertisement, contains the IP address of the leader.
    # 'candidate' - Current candidate for leader election.
    @app.post('/leader/<action>')
    def leader(action):
        global node_id, leader_random_number, self_random_number, leader_ip

        # Since we have a leader, no need to do anything.
        # Might be changed when adding fault tolerance features.
        if leader_elected():
            return None

        # If get leader advertisement, set the leader_ip and stop further leader election actions.
        if action == 'advertise':
            leader_ip = request.forms.get('leader_ip')
            leader_random_number = int(request.forms.get('leader_random_number'))
            print('Get leader ip:' + leader_ip)
            payload = {'leader_ip': leader_ip,
                       'leader_random_number': str(leader_random_number)}
            send_to_next_bg('advertise', payload)
            resend_unacked_messages()
            return None

        # Getting a candidate for the leader
        if action == 'candidate':
            candidate = request.forms.get('candidate')
            initiator = int(request.forms.get('initiator'))
            print 'candidate: ' + candidate
            candidate_id, candidate_random_number = tuple(map(lambda x: int(x), candidate.split('-')))

            # The message has traveled for an entire round.
            # The leader is current candidate
            if initiator == node_id:
                payload = {'leader_ip': '10.1.0.{}'.format(str(candidate_id)),
                           'leader_random_number': str(candidate_random_number)}
                send_to_next_bg('advertise', payload)
                resend_unacked_messages()
            else:
                # If I am a better candidate then update candidate and pass to next
                if self_random_number > candidate_random_number or \
                   self_random_number == candidate_random_number and node_id > candidate_id:
                    candidate = str(node_id) + "-" + str(self_random_number)
                payload = {'initiator': str(initiator),
                           'candidate': candidate}
                print payload
                send_to_next_bg('candidate', payload)
            return None
        if action == 'alive':
            return None
        else:
            return False

    # Advertise leader's identity to everyone.
    # def leader_advertise(leader_id, leader_random_number):
    #     path = '/leader/advertise'
    #     propagate_to_vessels_bg(path, payload={'leader_ip': '10.1.0.{}'.format(str(leader_id)),
    #                                            'leader_random_number': str(leader_random_number)})

    def send_to_next_bg(action, payload):
        t = Thread(target=send_to_next, args=(action, payload))
        t.start()

    # Send the action (in leader election) to the next node
    # in the virtual ring. Jump over if error occurs.
    def send_to_next(action, payload):
        global next_id, n_nodes, lock
        sent = False
        with lock:
            while not sent:
                try:
                    path = '/leader/' + action
                    print 'posting to :' + 'http://10.1.0.{}{}'.format(str(next_id), path)

                    url = 'http://10.1.0.{}{}'.format(str(next_id), path)
                    res = requests.post(url, data=payload)
                    print url + str(res)
                    sent = True
                except:
                    import traceback
                    traceback.print_exc()
                    print "Vessel #{} not responding. Trying to jump over.".format(next_id)
                    global next_id_generator
                    next_id = next(next_id_generator)

    # Initiate leader election procedure.
    def leader_election(self_random_number):
        global node_id  # maybe use arg as global instead?
        time.sleep(1)
        # Message format for candidate:
        # "node_id-random_number" (eg. "3-1324")
        candidate = str(node_id) + "-" + str(self_random_number)
        payload = {'initiator': str(node_id),
                   'candidate': candidate}
        send_to_next_bg('candidate', payload)

    # Check if the leader is still alive.
    def check_leader_liveness():
        global self_random_number, leader_ip, leader_random_number
        while True:
            time.sleep(20)
            if is_leader():
                #print("I am the leader.")
                continue

            #print("Checking leader liveness.")
            if not leader_elected():
                print("Leader is not elected yet.")
                continue
            try:
                path = '/leader/alive'
                url = 'http://{}{}'.format(get_leader_ip(), path)
                res = requests.post(url)
            except:
                # Leader is down. Initiate another round of leader election.
                leader_ip = None
                leader_random_number = None
                t = Thread(target=leader_election, args=(self_random_number,))
                t.start()

    # When a new leader is elected, check if there are unacked messages in waiting_ack.
    # If there are such messages, resend them to the new leader to be processed.
    def resend_unacked_messages():
        global waiting_ack

        # Wait for others to receive the leader advertisement
        time.sleep(2)

        if not leader_elected():
            return
        if len(waiting_ack) == 0:
            return
        else:
            print('Resending unacknowledged messages...')
            for key, val in waiting_ack.iteritems():
                print('Resending: ' + str(val))
                action, entry_id, entry = val
                payload = {'entry': entry, 'ack_key': key}
                if action == 'add':
                    contact_leader_bg('/prop_to_leader/add/-1', payload)
                elif action == 'modify':
                    contact_leader_bg('/prop_to_leader/modify/' + str(entry_id), payload)
                elif action == 'delete':
                    contact_leader_bg('/prop_to_leader/delete/' + str(entry_id), payload)
                else:
                    print("Unknown action!!!")

    # ------------------------------------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------------------------------------
    # a single example (index) should be done for get, and one for postGive it to the students-----------------------------------------------------------------------------------------------------
    # Execute the code

    def main():
        global vessel_list, node_id, app, self_random_number, n_nodes, next_id, next_id_generator

        port = 80
        parser = argparse.ArgumentParser(description='Your own implementation of the distributed blackboard')
        parser.add_argument('--id', nargs='?', dest='nid', default=1, type=int, help='This server ID')
        parser.add_argument('--vessels', nargs='?', dest='nbv', default=1, type=int, help='The total number of vessels present in the system')
        args = parser.parse_args()
        node_id = args.nid
        n_nodes = args.nbv
        next_id_generator = get_next_vessel_id()
        next_id = next(next_id_generator)

        # For debugging purpose
        if node_id in (1, 3, 5):
            sys.exit('Server down!')

        vessel_list = dict()
        # We need to write the other vessels IP, based on the knowledge of their number
        for i in range(1, args.nbv):
            vessel_list[str(i)] = '10.1.0.{}'.format(str(i))

        # The random number used for leader election
        self_random_number = random.randint(1, 2000)
        t = Thread(target=leader_election, args=(self_random_number,))
        t.daemon = True
        t.start()

        # Start checking if the leader is alive in every 3 seconds
        checker_t = Thread(target=check_leader_liveness)
        checker_t.daemon = True
        checker_t.start()

        try:
            run(app, host=vessel_list[str(node_id)], port=port)
        except Exception as e:
            print e
    # ------------------------------------------------------------------------------------------------------
    if __name__ == '__main__':
        main()
except Exception as e:
    traceback.print_exc()
    while True:
        time.sleep(60.)
