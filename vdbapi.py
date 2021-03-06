import json
from twisted.internet import reactor, defer
from twisted.web.client import Agent, readBody
from twisted.web.http_headers import Headers
from conf import config
from tools import clog
import database


syst = 'vdbapi'
UserAgentVdb = config['UserAgent']['vocadb'].encode('UTF-8')

def processVdbJson(body):
    clog.info('(processVdbJson) Received reply from VocaDB', syst)
    clog.debug('(processVdbJson) %s' % body, syst)
    body = body.decode('UTF-8')
    try:
        pbody = json.loads(body)
    except(ValueError):
        return defer.fail(None)
    try:
        if 'message' in pbody:
            clog.error(pbody['message'], syst)
    except(TypeError): # body is null (pbody is None)
        clog.error('(processVdbJson) null from Vocadb', syst)
        return defer.succeed(0)

    songId = pbody['id']
    return defer.succeed((body, songId))

def requestSongById(mType, mId, songId, userId, timeNow, method):
    """ Returns a deferred of Vocadb data of Song songId"""
    # check Song table to see if it's already saved
    ##if not, request data from VocaDB
    # UPDATE (or add) row in MediaSong table

    d = database.dbQuery(('data',), 'Song', songId=songId)
    d.addCallback(database.queryResult)
    d.addErrback(requestApiBySongId, songId, timeNow) # res is (body, songId)
    d.addCallbacks(database.insertMediaSong, apiError,
                   (mType, mId, songId, userId, timeNow, method))
    d.addErrback(ignoreErr)
    return d

def requestApiBySongId(res, songId, timeNow):
    """ Request video information from VocaDb API v2
    and save to the Song table """
    agent = Agent(reactor)
    url = 'http://vocadb.net/api/songs/%s?' % songId
    url += '&fields=artists,names&lang=romaji'
    clog.info('(requestApiBySongId) %s' % url, syst)
    d = agent.request('GET', url, Headers({'User-Agent':[UserAgentVdb]}))
    d.addCallback(readBody)
    d.addCallbacks(processVdbJson, apiError)
    d.addCallback(database.insertSong, timeNow)
    return d

def requestSongByPv(res, mType, mId, userId, timeNow, method):
    """ Returns a deferred of Vocadb data of Song songId"""
    # check mediaSong first
    # request data from VocaDB
    # UPDATE (or add) row in MediaSong table
    d = database.queryMediaSongRow(mType, mId)
    d.addCallback(mediaSongResult, mType, mId, userId, timeNow)
    d.addErrback(ignoreErr)
    return d

def mediaSongResult(res, mType, mId, userId, timeNow):
    clog.info('(mediaSongResult) %s' % res, syst)
    if res:
        return defer.succeed(res[0])
    else:
        dd = requestApiByPv(mType, mId, timeNow)
        method = 0
        dd.addErrback(apiError)
        dd.addCallback(database.insertMediaSongPv, mType, mId, userId, timeNow,
                       method)
        return dd

def requestApiByPv(mType, mId, timeNow):
    """ Request song information by Youtube or NicoNico Id,
    and save data to Song table """
    agent = Agent(reactor)
    if mType == 'yt':
        service = 'Youtube'
    else:
        service = 'NicoNicoDouga'
    url = 'http://vocadb.net/api/songs?pvId=%s&pvService=%s' % (mId, service)
    url += '&fields=artists,names&lang=romaji'
    clog.info('(requestApiByPv) %s' % url, syst)
    dd = agent.request('GET', str(url), Headers({'User-Agent':[UserAgentVdb]}))
    dd.addCallback(readBody)
    dd.addCallbacks(processVdbJson, apiError)
    dd.addCallback(database.insertSong, timeNow)
    return dd

def apiError(err):
    clog.error('(apiError) There was a problem with VocaDB API. %s' %
               err.value, syst)
    err.printDetailedTraceback()
    return err

def dbErr(err):
    clog.error('(dbErr) %s' % err.value, syst)
    return err

def ignoreErr(err):
    'Consume error and return a success'
    clog.error('(ignoreErr) %s' % err.value, syst)
    return defer.succeed(None)
