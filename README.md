# Distributed-Blackboard
A fault-tolerant distributed blackboard application.

Note: This project is initially a lab for Distributed System Course at Chalmers University of Technology.
The work is carried out in collaboration with my friend Oskar Lundström.

## To run the program
1. Install [Mininet](http://mininet.org/)
2. Run ```sudo python start.py```

## Design notes
1. Leader Election

In order to make every distributed server agree on the message sequence of the blackboard, the system needs to elect a leader to decide the sequence number for every message. We use a logical ring to organize this leader election phase. When the system starts, every server node will initiate leader election by sending a message to its next node in a ring manner. The message has a "candidate" field and an "initiator" field, both of which will be set to the node itself. Upon receiving such a message, every node will check if itself is a better leader than the one in the "candidate" field. If it is a better candidate (has a random number higher than the candidate in the message, if same, compare id), it will set itself as the candidate and propagate the message to the next node. When one node receives a message which has itself in the "initiator" field, it knows that the message has traveled for an entire round and a leader can be elected. Moreover, the leader is the one in the "candidate" field.

When a leader is elected, the node will record the identity of the leader, and propagate a leader advertisement message to the next node. Upon receiving leader advertisement, every node will set itself's leader identity and propagate this message. Some measures needs to be taken to prevent the message from propagating forever. At the end of leader election phase, every node will agree on the same leader.

2. Message submission, modification and deletion

When a node receives some message from the client side (a browser in this case), it will check if itself is a leader.

If it's a leader, it will handle the message in it's local memory directly and propagate this message to every other node for them to carry out the same behavior. In this procedure, the leader will decide the sequence number of the message and the order of the operation.

If the node is not a leader, it will propagate the required operation to the leader without doing anything in its local memory directly. Upon receiving this message, leader will carry out the operation in its local memory and propagate this message to every other node. Thus consistency of the blackboard is preserved.

3. Node fails during leader election phase

A node could fail during the leader election phase, which will result in the breaking of the logical ring. To overcome this problem, every node will jump over the node that is not responding to its request. Thus, no matter how many and which nodes are down we can still form a logical ring.

4. Leader fails

After a leader is elected, this leader could also fail. To tackle this problem, we adopt the heart beat solution. When a node starts, it will create a thread continuously checking if the leader is still alive every few seconds. It won't do anything if the leader responds correctly. But if the leader isn't responding, then it knows there is something wrong with the leader. It will set itself's leader to None and initiate a new round of leader election. After every node finds out that the leader is down, a new leader will be elected and the system can function normally again.

5. Preserve messages when leader fails and new leader is yet to be elected

Every node has a dictionary "waiting_ack". Before it sends any message to the leader, it will first add this message to "waiting_ack". Afterwards it will remove this message from "waiting_ack" if it receives the same message from the leader. Therefore, during the period when the leader is down, none of the message in "waiting_ack" will be acknowledged. When a new leader is elected, every node will iterate through its "waiting_ack" and send all those unacknowledged messages to the new leader. Thus we have a smooth transition between the switching of leadership.
