
import requests
import time
from threading import Thread

threads = set()
n = 0
for j in range(1,10):
    for i in range(1,8):
        if n % 3 == 0:
            thread = Thread(target=requests.post, args=('http://10.1.0.{}/board/{}/'.format(str(i),str(n)), {'delete':0,'entry':'MOD'+str(n)}))
            threads.add(thread)
            
        n += 1

for t in threads:
    t.start()
