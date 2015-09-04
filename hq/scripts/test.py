
import random

from hq.lib.hQUserServerProxy import hQUserServerProxy

# create a proxy to user-server
server = hQUserServerProxy()
server.run()

# send command and receive response
response = server.send( 'info' )
response = server.recv()

print response

jobs = []
for idx in range(1500):
    jobs.append( {'command': 'sleep {t}'.format(t=random.choice( range(10) ) ),
                  'info': "{i:3d}. sleep command".format(i=idx)} )

server.add_jobs( jobs )
