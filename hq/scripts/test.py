
from hq.lib.hQServerProxy import hQServerProxy

# create a proxy to user-server
server = hQServerProxy( serverType = 'user-server' )
server.run()

# send command and receive response
response = server.send( 'info' )
response = server.recv()

print response

