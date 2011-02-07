import random
import string
import logging

from zope.interface import implements
from zope.component import getUtility
from wokkel import client
from wokkel.subprotocols import StreamManager

from plone.messaging.twisted.interfaces import IDeferredXMPPClient
from plone.messaging.twisted.interfaces import IZopeReactor

logger = logging.getLogger('plone.messaging.twisted')


def randomResource():
    chars = string.letters + string.digits
    resource = 'auto-' + ''.join([random.choice(chars) for i in range(10)])
    return resource


class DeferredXMPPClient(object):

    implements(IDeferredXMPPClient)

    def execute(self, jid, password,
                callback, extra_handlers=[], errback=None):

        jid.resource=randomResource()

        factory = client.DeferredClientFactory(jid, password)
        for handler in extra_handlers:
            handler.setHandlerParent(factory.streamManager)

        d = client.clientCreator(factory)

        def disconnect(result):
            factory.streamManager.xmlstream.sendFooter()
            factory.streamManager.xmlstream.transport.connector.disconnect()
            return result

        def defaultErrBack(error_stanza):
            logger.error(error_stanza.getErrorMessage())
            logger.error("StanzaError: %s" % error_stanza.value.stanza.toXml())

        d.addCallback(callback)
        d.addCallback(disconnect)

        if errback:
            d.addErrback(errback)
        else:
            d.addErrback(defaultErrBack)

        zr = getUtility(IZopeReactor)
        zr.reactor.callFromThread(zr.reactor.connectTCP,
                                  "localhost", 5222, factory)
        return d


class XMPPClient(StreamManager):
    """
    Service that initiates an XMPP client connection.
    """

    def __init__(self, jid, password, extra_handlers=[],
                 host='localhost', port=5222):

        jid.resource=randomResource()

        self.jid = jid
        self.domain = jid.host
        self.host = host
        self.port = port
        self._state = None

        factory = client.HybridClientFactory(jid, password)

        # Setup StreamManager
        StreamManager.__init__(self, factory)
        for handler in extra_handlers:
            handler.setHandlerParent(self)

        zr = getUtility(IZopeReactor)
        zr.reactor.callFromThread(zr.reactor.connectTCP,
                                  self.host, self.port, self.factory)
        self._state = u'connecting'

    @property
    def state(self):
        return self._state

    def _authd(self, xs):
        """
        Called when the stream has been initialized.

        Save the JID that we were assigned by the server, as the resource might
        differ from the JID we asked for. This is stored on the authenticator
        by its constituent initializers.
        """
        self.jid = self.factory.authenticator.jid
        StreamManager._authd(self, xs)
        self._state = u'authenticated'

    def _connected(self, xs):
        self._state = u'connected'
        super(XMPPClient, self)._connected(xs)

    def _disconnected(self, _):
        self._state = u'disconnected'
        super(XMPPClient, self)._disconnected(_)
