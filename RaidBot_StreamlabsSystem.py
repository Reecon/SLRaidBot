#---------------------------
#   Import Libraries
#---------------------------
import os
import codecs
import sys
import json
import re
import datetime
import time
import threading
import socket
import errno
sys.path.append(os.path.join(os.path.dirname(__file__), "lib")) #point at lib folder for classes / references

import clr
clr.AddReference("IronPython.SQLite.dll")
clr.AddReference("IronPython.Modules.dll")
import sqlite3

#---------------------------
#   [Required] Script Information
#---------------------------
ScriptName = "RaidBot"
Website = "reecon820@gmail.com"
Description = "Logs raids and hosts so you can keep track of"
Creator = "Reecon820"
Version = "0.0.4.5"

#---------------------------
#   Settings Handling
#---------------------------
class RbSettings:
    def __init__(self, settingsfile=None):
        try:
            with codecs.open(settingsfile, encoding="utf-8-sig", mode="r") as f:
                self.__dict__ = json.load(f, encoding="utf-8")
        except:
            self.MinViewers = 10
            self.NewTarget = ""
            self.RemoveTarget = ""
            self.hostGoal = 100
            self.HideOffline = False

    def Reload(self, jsondata):
        self.__dict__ = json.loads(jsondata, encoding="utf-8")

    def Save(self, settingsfile):
        try:
            with codecs.open(settingsfile, encoding="utf-8-sig", mode="w+") as f:
                json.dump(self.__dict__, f, encoding="utf-8")
            with codecs.open(settingsfile.replace("json", "js"), encoding="utf-8-sig", mode="w+") as f:
                f.write("var settings = {0};".format(json.dumps(self.__dict__, encoding='utf-8')))
        except:
            Parent.Log(ScriptName, "Failed to save settings to file.")


#---------------------------
#   Define Global Variables
#---------------------------
global rbSettingsFile
rbSettingsFile = ""
global rbScriptSettings
rbScriptSettings = RbSettings()

global rbHtmlPath
rbHtmlPath = os.path.abspath(os.path.join(os.path.dirname(__file__), "RaidBot.html"))

global rbDatabase
rbDatabase = os.path.join(os.path.dirname(__file__), "raids.db")

global rbClientID
rbClientID = None

global rbApiTimer
rbApiTimer = None

global rbStopTimerEvent
rbStopTimerEvent = None

global rbIRCBot
rbIRCBot = None

global rbStopIRCBotEvent
rbStopIRCBotEvent = None

global rbHostOverlayPath
rbHostOverlayPath = os.path.abspath(os.path.join(os.path.dirname(__file__), "HostCounter.html"))

global rbActiveHostsFile
rbActiveHostsFile = os.path.abspath(os.path.join(os.path.dirname(__file__), "ActiveHosts.txt"))

global rbOAuthFile
rbOAuthFile = os.path.abspath(os.path.join(os.path.dirname(__file__), "OAuth.conf"))

#---------------------------
#   [Required] Initialize Data (Only called on load)
#---------------------------
def Init():

    #   Create Settings Directory
    directory = os.path.join(os.path.dirname(__file__), "Settings")
    if not os.path.exists(directory):
        os.makedirs(directory)

    #   Load settings
    global rbSettingsFile
    rbSettingsFile = os.path.join(os.path.dirname(__file__), "Settings\settings.json")
    global rbScriptSettings
    rbScriptSettings = RbSettings(rbSettingsFile)

    loadDatabase()

    updateUi()

    # read client id for api access from file
    try:
        with codecs.open(os.path.join(os.path.dirname(__file__), "clientid.conf"), mode='r', encoding='utf-8-sig') as f:
            global rbClientID
            rbClientID = f.readline()
    except Exception as err:
        Parent.Log(ScriptName, "{0}".format(err))

    # get channel user id
    userid = '0'
    headers = {'Client-ID': rbClientID, 'Accept': 'application/vnd.twitchtv.v5+json'}
    result = Parent.GetRequest("https://api.twitch.tv/kraken/users?login={0}".format(Parent.GetChannelName().lower()), headers)
    
    jsonResult = json.loads(result)
    if jsonResult['status'] != 200:
        Parent.Log(ScriptName, "lookup user: {0}".format(jsonResult))
        return
    else:
        jsonResult = json.loads(jsonResult['response'])
        if jsonResult['users']:
            jsonResult = jsonResult['users'][0]
            userid = jsonResult['_id']

    # set up and start timer
    global rbStopTimerEvent
    rbStopTimerEvent = threading.Event()
    global rbApiTimer
    rbApiTimer = RbApiTimer(rbStopTimerEvent, userid)
    rbApiTimer.start()

    global rbStopIRCBotEvent
    rbStopIRCBotEvent = threading.Event()
    global rbIRCBot
    rbIRCBot = IRCBot(rbStopIRCBotEvent)
    rbIRCBot.start()

    return

#---------------------------
#   [Required] Execute Data / Process messages
#---------------------------
def Execute(data):
    #log2file("{0}: {1} - {2}".format(data.UserName, data.Message, data.RawData))
    if data.IsRawData():
        rawTokens = data.RawData.split(' ')
        if len(rawTokens) < 3:
            return
        if rawTokens[2] == 'USERNOTICE': # we get raided
            #log2file("{}".format(data.RawData))
            #@badges=subscriber/6,partner/1;color=#E96BFF;display-name=TracyDoll;emotes=;flags=;id=af6af160-61a6-40fc-8168-cb0626e0e24b;login=tracydoll;mod=0;msg-id=raid;msg-param-displayName=TracyDoll;msg-param-login=tracydoll;msg-param-profileImageURL=https://static-cdn.jtvnw.net/jtv_user_pictures/baa2b832-084d-40d7-a2d2-912f9ed191ee-profile_image-70x70.png;msg-param-viewerCount=71;room-id=62983472;subscriber=1;system-msg=71\sraiders\sfrom\sTracyDoll\shave\sjoined\n!;tmi-sent-ts=1540113328399;turbo=0;user-id=127647856;user-type= :tmi.twitch.tv USERNOTICE #kaypikefashion
            if re.search("msg-id=raid;", rawTokens[0]):
                # get raiding channel and viewers
                #log2file("{}".format(data.RawData))
                raiderid = re.search("user-id=\d+;", rawTokens[0]).group(0).strip(";").split("=")[1]
                raidername = re.search("msg-param-login=\w+;", rawTokens[0]).group(0).strip(";").split("=")[1].lower()
                viewercount = re.search("msg-param-viewerCount=\d+;", rawTokens[0]).group(0).strip(";").split("=")[1]
                try:
                    viewercount = int(viewercount)
                except Exception as err:
                    log2file("Error parsing raid viewer number: {}".format(err.message))
                    Parent.Log(ScriptName, "Error parsing raid viewer number: {}".format(err.message))

                log2file("raid by {0} ({1}) for {2} viewers".format(raidername, raiderid, viewercount))
                
                if viewercount >= rbScriptSettings.MinViewers:
                    addTargetByIdAndName(raiderid, raidername)
                    addRaid(raidername, "raid", viewercount, targetid=raiderid)
                
        elif rawTokens[1] == "HOSTTARGET": # we host someone
            #log2file("{}".format(data.RawData))
            targetname = rawTokens[3][1:].lower()
            viewercount = int(rawTokens[4])
            #Parent.Log(ScriptName, "target: {0} - viewers: {1}".format(targetname, viewercount))

            if targetname != '-':
                targetUserId = getUserId(targetname)
                addTargetByIdAndName(targetUserId, targetname)
                addWeRaided(targetname, "host", viewercount, targetid=targetUserId)
                log2file("we hosted {0} ({1}) for {2} viewers".format(targetname, targetUserId, viewercount))
        
        # we raid someone (probably not communicated through chat)

    return

#---------------------------
#   [Required] Tick method (Gets called during every iteration even when there is no incoming data)
#---------------------------
def Tick():
    return

#---------------------------
#   [Optional] Parse method (Allows you to create your own custom $parameters) 
#---------------------------
def Parse(parseString, userid, username, targetid, targetname, message):
    return parseString

#---------------------------
#   [Optional] Reload Settings (Called when a user clicks the Save Settings button in the Chatbot UI)
#---------------------------
def ReloadSettings(jsonData):
    # Execute json reloading here
    jsonDict = json.loads(jsonData, encoding="utf-8")
    for target in jsonDict['RemoveTarget'].split(" "):
        removeTargetByName(target)
    for target in jsonDict['NewTarget'].split(" "):
        addTargetByName(target)

    loadDatabase()
    
    rbScriptSettings.Reload(jsonData)
    rbScriptSettings.Save(rbSettingsFile)

    jsonData = '{{ "goal_iteration": {} }}'.format(rbScriptSettings.hostGoal)
    Parent.BroadcastWsEvent("EVENT_HOST_COUNT", jsonData)
    return

#---------------------------
#   [Optional] Unload (Called when a user reloads their scripts or closes the bot / cleanup stuff)
#---------------------------
def Unload():
    # clean up timer
    if rbApiTimer != None and rbStopTimerEvent != None:
        rbStopTimerEvent.set()
    
    # clean up irc bot
    if rbIRCBot != None and rbStopIRCBotEvent != None:
        rbStopIRCBotEvent.set()
    return

#---------------------------
#   [Optional] ScriptToggled (Notifies you when a user disables your script or enables it)
#---------------------------
def ScriptToggled(state):
    return

def OpenWebsite():
    os.startfile(rbHtmlPath)
    loadDatabase()
    data = rbRaidsData
    data['client_id'] = rbClientID 
    data['hide_offline'] = "true" if rbScriptSettings.HideOffline else "false"
    dataString = json.dumps(data,indent=None)
    time.sleep(2) # wait till ui is loaded and connected
    Parent.BroadcastWsEvent("EVENT_RAID_DATA", dataString)
    return

def loadDatabase():
    # check if database exists
    if not os.path.exists(rbDatabase):
        conn = sqlite3.connect(rbDatabase)
        # create database structure
        c = conn.cursor()
        c.execute('CREATE TABLE targets (userid INTEGER PRIMARY KEY, username INTEGER, lastraid INTEGER, lastraided INTEGER)')
        c.execute('CREATE TABLE raids (raidid INTEGER PRIMARY KEY, username TEXT, type TEXT, viewers INTEGER, date INTEGER)')
        c.execute('CREATE TABLE weraided (raidid INTEGER PRIMARY KEY, username TEXT, type TEXT, viewers INTEGER, date INTEGER)')
        conn.commit()
        conn.close()
    
    data = {}

    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()
    
    # get all targets
    c.execute('SELECT * FROM targets')
    for row in c.fetchall():
        data[row[1]] = {"userid":row[0], "lastraid":row[2], "lastraided":row[3]}
    
    # add all raids to the targets
    c.execute('SELECT * FROM raids')
    for row in c.fetchall():
        raid = {"type": row[2], "viewers": row[3], "date": row[4]}
        
        if data[row[1]].has_key('raids'):
            data[row[1]]["raids"].append(raid)
        else:
            data[row[1]]["raids"] = [raid]
        
    # add all raids by us to the targets
    c.execute('SELECT * FROM weraided')
    for row in c.fetchall():
        raid = {"type": row[2], "viewers": row[3], "date": row[4]}
        
        if data[row[1]].has_key("weraided"):
            data[row[1]]["weraided"].append(raid)
        else:
            data[row[1]]["weraided"] = [raid]
    
    conn.close()
    
    global rbRaidsData
    rbRaidsData = data

def getDataAsString():
    dataString = ""

    dataString = json.dumps(rbRaidsData)

    return dataString

def addTargetByName(targetname):
    if not targetname:
        return
        
    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()
    targetid = getUserId(targetname)
    
    try:
        c.execute('INSERT OR IGNORE INTO targets (userid, username) VALUES({0}, "{1}")'.format(targetid, targetname))
        conn.commit()
    except Exception as err:
        Parent.Log(ScriptName, "Error adding target by name: {0}".format(err))
        
    conn.close()
    return

def addTargetByIdAndName(targetid, targetname):
    if not targetname or not targetid:
        return
    
    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()
    
    try: 
        c.execute('INSERT OR IGNORE INTO targets (userid, username) VALUES({0}, "{1}")'.format(targetid, targetname))
        conn.commit()
    except Exception as err:
        Parent.Log(ScriptName, "Error adding target by ID and Name: {0}".format(err))
    
    conn.close()
    return

def removeTargetByName(targetname):
    if (not targetname):
        return
    
    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()

    try:
        c.execute('DELETE FROM targets WHERE username like "{}"'.format(targetname))
        c.execute('DELETE FROM raids WHERE username like "{}"'.format(targetname))
        c.execute('DELETE FROM weraided WHERE username like "{}"'.format(targetname))
        conn.commit()
    except Exception as err:
        Parent.Log(ScriptName, "Error removing target: {}".format(err))

# to add raids when we get raiaded / hosted
def addRaid(targetname, raidtype, viewers, timestamp="now", targetid=None):
    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()
    if timestamp == "now":
        timestamp = int((datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds())
    try:
        c.execute('INSERT INTO raids (username, type, viewers, date) VALUES("{0}", "{1}", {2}, {3})'.format(targetname, raidtype, viewers, timestamp))
        userid = targetid
        if not targetid:
            userid = getUserId(targetname)

        c.execute('INSERT OR REPLACE INTO targets (userid, username, lastraid) VALUES({0}, "{1}", {2})'.format(userid, targetname, timestamp))
    except Exception as err:
        Parent.Log(ScriptName, "Error adding raid: {0}".format(err))

    conn.commit()
    conn.close()    
    return

# to add raids when we raided / hosted someone
def addWeRaided(targetname, raidtype, viewers, timestamp="now", targetid=None):
    conn = sqlite3.connect(rbDatabase)
    c = conn.cursor()
    if timestamp == "now":
        timestamp  = int((datetime.datetime.now() - datetime.datetime(1970, 1, 1)).total_seconds())
    try:
        c.execute('INSERT INTO weraided (username, type, viewers, date) VALUES("{0}", "{1}", {2}, {3})'.format(targetname, raidtype, viewers, timestamp))
        userid = targetid
        if not targetid:
            userid = getUserId(targetname)

        c.execute('INSERT OR REPLACE INTO targets (userid, username, lastraided) VALUES({0}, "{1}", {2})'.format(userid, targetname, timestamp))
    except Exception as err:
        Parent.Log(ScriptName, "Error adding 'we raided': {0}".format(err))
    conn.commit()
    conn.close()
    return

# lookup the twitch userid for a given username
def getUserId(username):
    headers = {'Client-ID': rbClientID, 'Accept': 'application/vnd.twitchtv.v5+json'}
    result = Parent.GetRequest("https://api.twitch.tv/kraken/users?login={0}".format(username.lower()), headers)
    jsonResult = json.loads(result)

    if jsonResult['status'] != 200:
        Parent.Log(ScriptName, "Error making API request: {0}".format(jsonResult))
        return
    else:
        jsonResult = json.loads(jsonResult['response'])
        if jsonResult['users']:
            jsonResult = jsonResult['users'][0]
        else:
            Parent.Log(ScriptName, "Unknown Twitch Username")
            return
    return int(jsonResult['_id'])

def copyOverlayPath():
    command = "echo " + rbHostOverlayPath + " | clip"
    os.system(command)
    return

def copyHostsFilePath():
    command = "echo " + rbActiveHostsFile + " | clip"
    os.system(command)
    return

def updateUi():
    ui = {}
    UiFilePath = os.path.join(os.path.dirname(__file__), "UI_Config.json")
    try:
        with codecs.open(UiFilePath, encoding="utf-8-sig", mode="r") as f:
            ui = json.load(f, encoding="utf-8")
    except Exception as err:
        Parent.Log(ScriptName, "Error readin UI file: {0}".format(err))

    # update ui with loaded settings
    ui['MinViewers']['value'] = rbScriptSettings.MinViewers
    ui['NewTarget']['value'] = rbScriptSettings.NewTarget
    ui['RemoveTarget']['value'] = rbScriptSettings.RemoveTarget
    ui['hostGoal']['value'] = rbScriptSettings.hostGoal
    ui['HideOffline']['value'] = rbScriptSettings.HideOffline

    try:
        with codecs.open(UiFilePath, encoding="utf-8-sig", mode="w+") as f:
            json.dump(ui, f, encoding="utf-8", indent=4, sort_keys=True)
    except Exception as err:
        Parent.Log(ScriptName, "Error writing UI file: {0}".format(err))

def log2file(message):
    logFilePath = os.path.join(os.path.dirname(__file__), "log.txt")
    try:
        with codecs.open(logFilePath, encoding="utf-8", mode="a+") as f:
            line = "{0} -- {1}".format(datetime.datetime.now(), message)
            f.write(line + "\n")
    except Exception as err:
        Parent.Log(ScriptName, "Error writing log file: {0}".format(err))

#---------------------------
#   Host API Polling
#---------------------------
class RbApiTimer(threading.Thread):
    def __init__(self, event, id):
        threading.Thread.__init__(self)
        self.stopped = event
        self.id = id

    def run(self):
        while not self.stopped.wait(60.0):
            # make api call
            timerHeaders = {'Accept': 'application/json'}
            timerResult = Parent.GetRequest("https://tmi.twitch.tv/hosts?&target={0}".format(self.id), timerHeaders)
            timerJsonResult = json.loads(timerResult)
            
            if timerJsonResult['status'] == 200:
                timerJsonResult = json.loads(timerJsonResult['response'])
                
                hosts = timerJsonResult['hosts']
                rbHostCount = len(hosts)

                # send data to overlay
                timerJsonData = '{{ "current_hosts": {} }}'.format(rbHostCount)
                Parent.BroadcastWsEvent("EVENT_HOST_COUNT", timerJsonData)
                
                # save data to file
                try:
                    with codecs.open(rbActiveHostsFile, encoding="utf-8-sig", mode="w+") as f:
                        f.write("{}".format(rbHostCount))
                except Exception as err:
                    Parent.Log(ScriptName, "{0}".format(err))
            else:
                Parent.Log(ScriptName, "Error polling hosts: {}".format(timerJsonResult['status']))
            

#---------------------------
#   Twitch Chat Connection
#---------------------------
class IRCBot(threading.Thread):

    def __init__(self, event):
        threading.Thread.__init__(self)
        self.stopped = event
        self.server = "irc.twitch.tv"
        self.port = 6667
        self.user = Parent.GetChannelName().lower()
        self.hostchannel = '#' + Parent.GetChannelName().lower()

        try:
            with codecs.open(rbOAuthFile, encoding="utf-8-sig", mode="r") as f:
                for line in f:
                    line = line.strip()
                    if len(line) > 0:
                        if line[0] != '#':
                            self.pw = line
        except Exception as err:
            log2file("Error reading OAuth file: {0}".format(err))
            Parent.Log(ScriptName, "Error reading OAuth file: {0}".format(err))
        
        
        self.ircsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.ircsock.settimeout(0.5)
        
    def connect_to_server_(self):
        log2file("IRCBot:: connect")
        self.ircsock.connect((self.server, self.port))
        log2file("IRCBot:: user")
        print(self.ircsock.send(("USER " + self.user + " " + self.user + " " + self.user + " : " + self.user + "\n").encode("UTF-8")))
        log2file("IRCBot:: pass")
        print(self.ircsock.send(("PASS " + self.pw + "\n").encode("UTF-8")))
        log2file("IRCBot:: nick")
        print(self.ircsock.send(("NICK " + self.user + "\n").encode("UTF-8")))
        self.join_channel_(self.hostchannel)
        log2file("IRCBot:: connected to " + self.hostchannel)
    
    def join_channel_(self,chan):
        log2file("IRCBot:: join")
        print(self.ircsock.send(("JOIN "+ chan + "\n").encode("UTF-8")))
    
    def pong(self):
        #log2file("IRCBot:: pong")
        print(self.ircsock.send(("PONG :Pong\n").encode("UTF-8")))
        
    def sendmsg(self, chan, msg):
        log2file("IRCBot:: send")
        print(self.ircsock.send(("PRIVMSG " + chan + " :" + msg + "\n").encode("UTF-8")))
        
    def shutdown(self):
        log2file("IRCBot:: part")
        print(self.ircsock.send(("PART "+ self.hostchannel + "\n").encode("UTF-8")))
        log2file("IRCBot:: quit")
        print(self.ircsock.send(("QUIT off for now").encode("UTF-8")))
        log2file("IRCBot:: close socket")
        self.ircsock.close()
    
    def run(self):
        # connect to irc
        self.connect_to_server_()

        # wait for a new message to process
        while not self.stopped.wait(0.1):
            try: 
                ircmsg = self.ircsock.recv(4096)
            except socket.timeout, e:
                err = e.args[0]
                if err == 'timed out':
                    continue
            except socket.error, e:
                # a "real" error occurred
                log2file("IRCBot:: Error reading irc socket: {}".format(e.message))
                #Parent.Log(ScriptName, "Error reading irc socket: {}".format(e.message))
                time.sleep(2)
            else:
                ircmsg = ircmsg.decode("UTF-8")
                ircmsg = ircmsg.strip('\r\n')
                #log2file("IRCBot:: " + ircmsg)
                
                if ircmsg.find("PING :") != -1:
                    self.pong()

                #only consume host notifications
                if re.search(":jtv.*:.*is\snow\shosting\syou", ircmsg):
                    # :jtv!jtv@jtv.tmi.twitch.tv PRIVMSG reecon820 :care_o_bot is now hosting you.
                    #log2file("IRCBot:: {}".format(ircmsg))
                    message = ircmsg

                    if re.search(":jtv!.*:.*is\snow\shosting\syou", message):# or (rbScriptSettings.autoHosts and re.search("is\snow\sauto\shosting\syou", message)): # autohost message not sent anymore
                        hostType = "host" if re.search(":jtv.*:.*is\snow\shosting\syou", message) else "autohost"
                        hostStringTokens = message.split(":")[2].split(" ")
                        hostername = hostStringTokens[0].lower()
                        viewers = 0
                        if hostType == "host":
                            # :jtv!jtv@jtv.tmi.twitch.tv PRIVMSG kaypikefashion :Eldirtysquirrel is now hosting you for up to 93 viewers.
                            try:
                                viewers = int(hostStringTokens[8]) if len(hostStringTokens) > 5 else 0
                            except Exception as err:
                                log2file("Error parsing host viewercount: {}".format(err.message))
                                Parent.Log(ScriptName, "Error parsing host viewercount: {}".format(err.message))
                        else:
                            # in case of autohost 
                            # :jtv!jtv@jtv.tmi.twitch.tv PRIVMSG kaypikefashion :reecon820 is now auto hosting you for up to 3 viewers.
                            try:
                                viewers = int(hostStringTokens[9]) if len(hostStringTokens) > 5 else 0
                            except Exception as err:
                                log2file("Error parsing auto host viewercount: {}".format(err.message))
                                Parent.Log(ScriptName, "Error parsing auto host viewercount: {}".format(err.message))

                        log2file("IRCBot:: host by {0} for {1} viewers".format(hostername, viewers))

                        if viewers >= rbScriptSettings.MinViewers:
                            #Parent.Log(ScriptName, "{0} {2} for {1} viewers".format(hostername, viewers, hostType))
                            hosterId = getUserId(hostername)    # only poll api once per host, this is bad enough
                            addTargetByIdAndName(hosterId, hostername)
                            addRaid(hostername, hostType, viewers, targetid=hosterId)
        self.shutdown()
                    