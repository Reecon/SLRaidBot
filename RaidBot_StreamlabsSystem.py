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
sys.path.append(os.path.join(os.path.dirname(__file__), "lib")) #point at lib folder for classes / references

import clr
clr.AddReference("IronPython.SQLite.dll")
clr.AddReference("IronPython.Modules.dll")
import sqlite3

#   Import your Settings class
from Settings_Module import MySettings
#---------------------------
#   [Required] Script Information
#---------------------------
ScriptName = "RaidBot"
Website = "reecon820@gmail.com"
Description = "Logs raids and hosts so you can keep track of"
Creator = "Reecon820"
Version = "0.0.1.0"

#---------------------------
#   Define Global Variables
#---------------------------
global SettingsFile
SettingsFile = ""
global ScriptSettings
ScriptSettings = MySettings()

global HtmlPath
HtmlPath = os.path.abspath(os.path.join(os.path.dirname(__file__), "RaidBot.html"))

global Database
Database = os.path.join(os.path.dirname(__file__), "raids.db")

global ClientID
ClientID = None
#---------------------------
#   [Required] Initialize Data (Only called on load)
#---------------------------
def Init():

    #   Create Settings Directory
    directory = os.path.join(os.path.dirname(__file__), "Settings")
    if not os.path.exists(directory):
        os.makedirs(directory)

    #   Load settings
    global SettingsFile
    SettingsFile = os.path.join(os.path.dirname(__file__), "Settings\settings.json")
    global ScriptSettings
    ScriptSettings = MySettings(SettingsFile)

    ui = {}
    UiFilePath = os.path.join(os.path.dirname(__file__), "UI_Config.json")
    try:
        with codecs.open(UiFilePath, encoding="utf-8-sig", mode="r") as f:
            ui = json.load(f, encoding="utf-8")
    except Exception as err:
        Parent.Log(ScriptName, "{0}".format(err))

    # update ui with loaded settings
    ui['MinViewers']['value'] = ScriptSettings.MinViewers
    ui['NewTarget']['value'] = ScriptSettings.NewTarget
    ui['RemoveTarget']['value'] = ScriptSettings.RemoveTarget

    try:
        with codecs.open(UiFilePath, encoding="utf-8-sig", mode="w+") as f:
            json.dump(ui, f, encoding="utf-8", indent=4, sort_keys=True)
    except Exception as err:
        Parent.Log(ScriptName, "{0}".format(err))

    loadDatabase()

    # read client id for api access from file
    try:
        with codecs.open(os.path.join(os.path.dirname(__file__), "clientid.conf"), mode='r', encoding='utf-8-sig') as f:
            global ClientID
            ClientID = f.readline()
    except Exception as err:
        Parent.Log(ScriptName, "{0}".format(err))

    return

#---------------------------
#   [Required] Execute Data / Process messages
#---------------------------
def Execute(data):
    
    if data.IsRawData():
        if "USERNOTICE" in data.RawData: # we get raided
            if "msg-id=raid" in data.RawData:
                # get raiding channel and viewers
                raiderid = re.search("user-id=\d", data.RawData).group(0).split("=")[1]
                raidername = re.search("msg-param-login=.*;", data.RawData).group(0).strip(";").split("=")[1]
                viewercount = re.search("msg-param-viewerCount=\d", data.RawData).split("=")[1]
                
                addTargetByIdAndName(raiderid, raidername)
                addRaid(raidername, "raid", viewercount)
                
        elif "HOSTTARGET" in data.RawData: # we host someone
            tokens = data.RawData.split(" ")
            targetname = tokens[3][1:]
            viewercount = int(tokens[4])
            Parent.Log(ScriptName, "target: {0} - viewers: {1}".format(targetname, viewercount))

            if targetname != '-':
                addTargetByName(targetname)
                addWeRaided(targetname, "host", viewercount)

        elif "PRIVMSG" in data.RawData: # we get hosted
            # :jtv!jtv@jtv.tmi.twitch.tv PRIVMSG care_o_bot :Reecon820 is now hosting you.
            
            message = data.RawData

            if re.search(":jtv.*:.*is\snow\shosting\syou", message): # or (ScriptSettings.autohosts and re.search(":jtv.*:.*is\snow\sauto\shosting\syou", message)):
                
                Parent.Log(ScriptName, "got hosted: {}".format(message))

                hostType = "host" if re.search(":jtv.*:.*is\snow\shosting\syou", message) else "autohost"
                hostStringTokens = message.split(":")[2].split(" ")
                hostername = hostStringTokens[0]
                viewers = 0
                if hostType == "host":
                    viewers = int(hostStringTokens[9]) if len(hostStringTokens) > 5 else 0
                else:
                    viewers = int(hostStringTokens[10]) if len(hostStringTokens) > 5 else 0

                Parent.Log(ScriptName, "{0} {2} for {1} viewers".format(hostername, viewers, hostType))

                addTargetByName(hostername)
                addRaid(hostername, hostType, viewers)

        # we raid someone

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
    
    ScriptSettings.Reload(jsonData)
    ScriptSettings.Save(SettingsFile)
    return

#---------------------------
#   [Optional] Unload (Called when a user reloads their scripts or closes the bot / cleanup stuff)
#---------------------------
def Unload():
    return

#---------------------------
#   [Optional] ScriptToggled (Notifies you when a user disables your script or enables it)
#---------------------------
def ScriptToggled(state):
    return

def OpenWebsite():
    os.startfile(HtmlPath)
    loadDatabase()
    data = RaidsData
    data['client_id'] = ClientID 
    dataString = json.dumps(data,indent=None)
    time.sleep(2) # wait till ui is loaded and connected
    Parent.BroadcastWsEvent("EVENT_RAID_DATA", dataString)
    return

def loadDatabase():
    # check if database exists
    if not os.path.exists(Database):
        conn = sqlite3.connect(Database)
        # create database structure
        c = conn.cursor()
        c.execute('CREATE TABLE targets (userid INTEGER PRIMARY KEY, username INTEGER, lastraid INTEGER, lastraided INTEGER)')
        c.execute('CREATE TABLE raids (raidid INTEGER PRIMARY KEY, username TEXT, type TEXT, viewers INTEGER, date INTEGER)')
        c.execute('CREATE TABLE weraided (raidid INTEGER PRIMARY KEY, username TEXT, type TEXT, viewers INTEGER, date INTEGER)')
        conn.commit()
        conn.close()
    
    data = {}

    conn = sqlite3.connect(Database)
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
    
    global RaidsData
    RaidsData = data
    return

def getDataAsString():
    dataString = ""

    dataString = json.dumps(RaidsData)

    return dataString

def addTargetByName(targetname):
    if not targetname:
        return
        
    conn = sqlite3.connect(Database)
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
    
    conn = sqlite3.connect(Database)
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
    
    conn = sqlite3.connect(Database)
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
    conn = sqlite3.connect(Database)
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
    conn = sqlite3.connect(Database)
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
    headers = {'Client-ID': ClientID, 'Accept': 'application/vnd.twitchtv.v5+json'}
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


