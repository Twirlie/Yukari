from ircClient import IrcProtocol, IrcFactory
from cyClient import CyProtocol, WsFactory
from conf import config
import database, tools
import time, sys
from twisted.internet import reactor
from twisted.internet.defer import Deferred
from twisted.web.client import Agent, readBody
from twisted.python import log
from twisted.manhole import telnet
from autobahn.twisted.websocket import connectWS

class Connections:
    """ Handles connections to a Cytube server and IRC, as well as
        any communication between them."""
    
    def __init__(self):
        # False = Offline, True = Online, None = has shutdown
        self.irc = False
        self.cy = False

        # Wether to restart when disconnected
        self.ircRestart = True
        self.cyRestart = True

    def cyPost(self):
        """ Send a POST request to Cytube for a server session id
        and start the connection process """
        agent = Agent(reactor)
        url = 'http://%s:%s/socket.io/1/' % (config['Cytube']['url'],
                                             config['Cytube']['port'])
        d = agent.request('POST', str(url))
        d.addCallbacks(readBody, self.cyPostErr) # POST response
        d.addCallback(self.processBody)
        d.addCallback(self.cySocketIo)

    def cyPostErr(self, err):
        print err 

    def processBody(self, body):
        print "RECEIVED %s " % body 

        msg = body.split(',')
        sid = msg[0][:msg[0].find(':')]
        ws = 'ws://%s:%s/socket.io/1/websocket/%s/' % (config['Cytube']['url'],
              int(config['Cytube']['port']), sid)
        return ws

    def cySocketIo(self, url):
        print "cySocketIo %s" % url
        self.wsFactory = WsFactory(url)
        self.wsFactory.handle = self
        connectWS(self.wsFactory)

    def ircConnect(self):
        self.ircFactory = IrcFactory(config['irc']['channel'])
        self.ircFactory.handle = self
        reactor.connectTCP(config['irc']['url'], int(config['irc']['port']),
                           self.ircFactory)

    def recIrcMsg(self, user, channel, msg):
        if self.cy:
            user = user.split('!', 1)[0] # takes out the extra info in the name
            msgf = '(%s) %s' % (user, msg)
            self.wsFactory.prot.sendChat(msgf)
        self.processCommand(user, msg)

    def recCyMsg(self, user, msg):
        if self.irc:
            #s = TagStrip()
            tools.chatFormat.feed(msg)
            cleanMsg = tools.chatFormat.get_text()
            # reset so we can use the same instance
            tools.chatFormat.close()
            tools.chatFormat.result = []
            tools.chatFormat.reset()
            cleanMsg = '(%s) %s' % (user, cleanMsg)
            self.sendToIrc(cleanMsg)
        self.processCommand(user, msg)

    def processCommand(self, user, msg):
        if msg.startswith('$'):
            command = msg.split('$')[1]
            thunk = getattr(self, '_com_%s' % (command,), None)
            if thunk is not None:
                thunk(user, msg)

    def _com_greet(self, user, msg):
        msg = 'Nice to meet you, %s!' % user
        reactor.callLater(0.05, self.sendChats, msg)

    def sendToCy(self, msg, modflair=False):
        if self.cy:
            self.wsFactory.prot.sendChat(msg, modflair)

    def sendToIrc(self, msg):
        if self.irc:
            self.ircFactory.prot.sendChat(str(config['irc']['channel']), msg)

    def sendChats(self, msg, modflair=False):
        self.sendToIrc(msg)
        self.sendToCy(msg, modflair)

    def cleanup(self):
        """ Prepares for shutdown """
        print 'Cleaning up for shutdown!'
        self.done = Deferred()
        if self.irc:
            self.ircFactory.prot.partLeave('Shutting down.')
        if self.cy:
            self.wsFactory.prot.cleanUp()
        return self.done

    def doneCleanup(self, protocol):
        """ Fires the done deferred, which unpauses the shutdown sequence """
        # If the application is stuck after Ctrl+C due to a bug,
        # use telnet(manhole) to manually fire the 'done' deferred.
        if protocol == 'irc':
            self.irc = None
            print 'Done shutting down IRC.'
        elif protocol == 'cy':
            self.cy = None
            print 'Done shutting down Cy.'
        if self.irc is not True and self.cy is not True:
            self.done.callback(None)

def createShellServer(obj):
    """ Creates an interactive shell interface to send and receive output 
    while the program is running. Connection's instance yukari is named y.
    e.g. dir(y), will list all of yukari's names"""

    print 'Creating shell server instance...'
    factory = telnet.ShellFactory()
    port = reactor.listenTCP(int(config['telnet']['port']), factory)
    factory.namespace['y'] = obj
    factory.username = config['telnet']['username']
    factory.password = config['telnet']['password']
    log.msg('starting shell server...', system='Shell')
    return port

log.startLogging(sys.stdout)
yukari = Connections()
yukari.cyPost()
yukari.ircConnect()
reactor.callWhenRunning(createShellServer, yukari)
reactor.addSystemEventTrigger('before', 'shutdown', yukari.cleanup)
reactor.run()
