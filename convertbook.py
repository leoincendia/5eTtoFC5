# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab : #
import xml.etree.cElementTree as ET
import json
import re
import sys
import os
import tempfile
import shutil
import argparse
import uuid
import copy
from slugify import slugify
import utils
import time
from text_to_num import alpha2digit
from wand.image import Image
import zipfile
import urllib.parse
import urllib.request
import math
import pytesseract
import PIL.Image
import PIL.ImageOps

# Argument Parser
parser = argparse.ArgumentParser(
    description="Converts 5eTools json files to FC5 compatible XML files.")
parser.add_argument(
    '-a',
    dest="adventure",
    action='store_const',
    const=True,
    default=False,
    help="is an adventure")
parser.add_argument(
    '-v',
    dest="verbose",
    action='store_const',
    const=True,
    default=False,
    help="verbose output (default: false)")
parser.add_argument(
    '-m',
    dest="manualbreak",
    action='store_const',
    const=True,
    default=False,
    help="manual breakout of area pages (default: false)")
parser.add_argument(
    '-o',
    dest="output",
    action='store',
    default=None,
    help="output into given output (default: book-[id].module)")
parser.add_argument(
    dest="book",
    action='store',
    default=False,
    nargs='?',
    help="id for book to convert")

args = parser.parse_args()

tempdir = tempfile.mkdtemp(prefix="convertbook_")

nsuuid = uuid.UUID("17f0f0ec-e658-4b3f-911a-7c585a6ec519")

numbers = ['zero','one','two','three','four']
stats = {"str":"Strength","dex":"Dexterity","con":"Constitution","int":"Intelligence","wis":"Wisdom","cha":"Charisma"}

def trim(im):
    im = im.convert('L').point(lambda x : 255 if x > 128 else 0,mode='1')
    for x in range(im.width):
        for y in range(im.height):
            pix = im.getpixel((x,y))
            if pix == 255:
                im.putpixel((x,y),0)
            else:
                break
    for x in range(im.width-1,0,-1):
        for y in range(im.height-1,0,-1):
            pix = im.getpixel((x,y))
            if pix == 255:
                im.putpixel((x,y),0)
            else:
                break
    im = im.convert('L').point(lambda x : 255 if x > 200 else 0,mode='1')
    for x in range(im.width):
        for y in range(im.height):
            pix = im.getpixel((x,y))
            if pix == 0:
                im.putpixel((x,y),255)
            else:
                break
    for x in range(im.width-1,0,-1):
        for y in range(im.height-1,0,-1):
            pix = im.getpixel((x,y))
            if pix == 0:
                im.putpixel((x,y),255)
            else:
                break
    x1 = 0
    x2 = 0
    y1 = 0
    y2 = 0
    for x in range(im.width):
        ok = True
        for y in range(im.height):
            if im.getpixel((x,y)) < (255):
                ok = False
                break
        if ok:
            x1 = x
        else:
            break
    for y in range(im.height):
        ok = True
        for x in range(im.width):
            if im.getpixel((x,y)) < (255):
                ok = False
                break
        if ok:
            y1 = y
        else:
            break
    for x in range(im.width,0,-1):
        ok = True
        for y in range(im.height):
            if im.getpixel((x-1,y)) < (255):
                ok = False
                break
        if ok:
            x2 = x
        else:
            break
    wait = True
    for y in range(y1+1,im.height):
        ok = True
        for x in range(im.width):
            if im.getpixel((x,y)) < (255):
                ok = False
                break
        if ok:
            y2 = y
            wait = False
        if not wait:
            break
    if x1 < x2 and y1 < y2:
        im = PIL.ImageOps.expand(im.crop((x1,y1,x2,y2)),10,255)
        return im.resize((round(im.width*(70/im.height)),round(im.height*(70/im.height))))
    else:
        return im

def fixTags(s,d=None,p=None,noencounter=False,nodice=False):
    s = re.sub(r'{@([bi]) (.*?)}',r'<\1>\2</\1>', s)
    s = re.sub(r'{@link (.*?)\|(.*?)?}', r'<a href="\2">\1</a>', s)
    def dice(m):
        title = ''
        roll = re.sub(r'#\$.*default=([0-9]*).*\$#',r'\1',m.group(1))
        if type(p) == dict and p and 'name' in p:
            title = '/{}'.format(urllib.parse.quote(p['name']))
        elif not p and type(d) == dict and d and 'name' in d:
            title = '/{}'.format(urllib.parse.quote(d['name']))
        if m.group(2):
            return '<a href="/roll/{0}{2}">{1}</a>'.format(roll,m.group(2),title)
        else:
            return '<a href="/roll/{0}{1}">{0}</a>'.format(roll,title)
    def dicepre(m):
        if m.group(1):
            return m.group(0)
        else:
            return "{{@dice {}}}".format(m.group(2))
    if not nodice:
        s = re.sub(r'(<a [^>]*>|{@[^}]*)?([0-9]*[dD][0-9]+( *[+-] *([0-9]*[dD][0-9]+( *[+-] *[0-9]+)?|[0-9]+))?)', dicepre, s)
        s = re.sub(r'{@dice (.*?)(?:\|(.*?))?}', dice, s)
    if args.adventure and d and re.search(r'{@creature (.*?)(\|(.*?))?(\|(.*?))?}', s) and not re.match(r'^{@creature (.*?)(\|(.*?))?(\|(.*?))?}$',s) and not noencounter:
        s2 = alpha2digit(s,"en")
        encounterbaseslug = d['currentslug'] + "-encounter"
        encounterslug = encounterbaseslug + str(len([i for i in slugs if encounterbaseslug in i]))
        sectionuuid = str(uuid.uuid5(bookuuid,encounterslug))
        encounter = ET.SubElement(module, 'encounter', { 'id': sectionuuid, 'parent': d['subsection'] if 'subsection' in d else d['currentpage'], 'sort': str(99+len([i for i in slugs if encounterbaseslug in i])) })
        encountername = "Encounter {}: {}".format(len([i for i in slugs if encounterbaseslug in i])+1,p['name'] if 'name' in p and type(p) == dict else d['subsectionname'] if 'subsectionname' in d else d['pagetitle'])
        #if encountername.startswith("Encounter 3: C6."):
        #    raise RuntimeError("Stop...")
        ET.SubElement(encounter,'name').text = encountername
        ET.SubElement(encounter,'description').text = utils.remove5eShit(s)
        ET.SubElement(encounter,'slug').text = encounterslug
        slugs.append(encounterslug)
        #if parent:
        #    parent['entries'].append('<a href="/encounter/{}">{}</a>'.format(encounterslug,encountername))
        s = '<p style="text-align: right; font-style: italic; font-weight: bold; text-decoration: underline; font-variant:small-caps;"><a href="/encounter/{}">Encounter {}</a></p>\n{}'.format(encounterslug,len([i for i in slugs if encounterbaseslug in i]),s)
        monsterids = []
        for creature in re.finditer(r'([0-9]+)?( [A-Za-z]*)? ?{@creature (.*?)(\|(.*?))?(\|(.*?))?}',s2):
            for i in range(len(creature.group(3))):
                if creature.group(3)[i].upper() not in monsterids:
                    monsterid = creature.group(3)[i].upper()
                    monsterids.append(monsterid)
                    break
            for i in range(int(creature.group(1) if creature.group(1) else "1")):
                combatant = ET.SubElement(encounter,'combatant')
                ET.SubElement(combatant,'label').text = "{}{}".format(monsterid,i+1) 
                monster = slugify(creature.group(3))
                if monster == "will-o-wisp":
                    monster = "will-o--wisp"
                ET.SubElement(combatant,'monster',{ 'ref': "/monster/{}".format(monster) })
    def createMLink(matchobj):
        monster = slugify(matchobj.group(1))
        if monster == "will-o-wisp":
            monster = "will-o--wisp"
        return "<a href=\"/monster/{}\">{}</a>".format(monster,matchobj.group(5) if matchobj.group(5) else matchobj.group(1))
    s = re.sub(r'{@creature (.*?)(\|(.*?))?(\|(.*?))?}', createMLink, s)
    def createILink(matchobj):
        return "<a href=\"/item/{}\">{}</a>".format(slugify(matchobj.group(1)),matchobj.group(1))
    s = re.sub(r'{@item (.*?)(\|.*?)?}', createILink, s)
    def createSLink(matchobj):
        return "<a href=\"/spell/{}\">{}</a>".format(slugify(matchobj.group(1)),matchobj.group(1))
    s = re.sub(r'{@spell (.*?)(\|.*?)?}', createSLink, s)
    def createPLink(matchobj):
        return "<a href=\"/page/{}\">{}</a>".format(slugify(matchobj.group(1)),matchobj.group(1))
    s = re.sub(r'{@class (.*?)}', createPLink, s)
    s = re.sub(r'{@condition (.*?)}', createPLink, s)
    def getAreaLink(m):
        path = idSearch(m.group(2))
        if not path:
            return "{{@{} {}|{}|{}}}".format("adventure" if args.adventure else "book",m.group(1),book["id"],9999)
        if path == "/page/{}#{}".format(d['currentslug'],m.group(2)):
            path = "#{}".format(m.group(2))
        return "<a href=\"{}\">{}</a>".format(path,m.group(1))
    s = re.sub(r'{@area (.*?)\|(.*?)(\|.*?)?}',getAreaLink,s)
    def createALink(matchobj):
        chno = int(matchobj.group(5)) if matchobj.group(5) else 0
        sectitle = None
        if matchobj.group(3) != book["id"]:
            with open("./data/{}s.json".format(matchobj.group(1)),encoding='utf-8') as f:
                    ab = json.load(f)
                    f.close()
            for otherbook in ab[matchobj.group(1)]:
                if otherbook["id"].lower() != matchobj.group(3).lower():
                    continue
                otherbookid = otherbook["id"]
                sec = otherbook["contents"][chno]
                if 'ordinal' in sec:
                    sectitle = "{} {}: {}".format(sec['ordinal']['type'].title(),sec['ordinal']['identifier'],sec['name'])
                else:
                    sectitle = "{}".format(sec['name'])
            if not sectitle:
                return matchobj.group(2)
            return "<a href=\"/module/{}/page/{}\">{}</a>".format(uuid.uuid5(nsuuid,otherbookid),slugify(sectitle),matchobj.group(2))
        else:
            if chno > len(bookref["contents"]):
                chno = 0
                for i in range(len(bookref["contents"])):
                        if 'ordinal' in bookref["contents"][i] and matchobj.group(2) == "{} {}".format(bookref["contents"][i]['ordinal']['type'],bookref["contents"][i]['ordinal']['identifier']):
                            chno = i
            sec = bookref["contents"][chno]
            if matchobj.group(7) and 'headers' in sec:
                for header in sec['headers']:
                    if type(header) == dict and header['header'] == matchobj.group(7):
                        sectitle = header['header']
                    elif str(header) == matchobj.group(7):
                        sectitle = header
            elif 'ordinal' in sec:
                sectitle = "{} {}: {}".format(sec['ordinal']['type'].title(),sec['ordinal']['identifier'],sec['name'])
            else:
                sectitle = "{}".format(sec['name'])
            if not sectitle:
                return matchobj.group(2)
            return "<a href=\"/page/{}\">{}</a>".format(slugify(sectitle),matchobj.group(2))
        #if matchobj.group(3):
        #    print("using slug:",matchobj.group(3))
        #    return "<a href=\"/page/{}\">{}</a>".format(slugify(matchobj.group(3)),matchobj.group(1))
        #else:
        #    print("searching contents",matchobj.group(1))
        #    for sec in bookref["contents"]:
        #        if 'ordinal' in sec:
        #            if matchobj.group(1) == "{} {}".format(sec['ordinal']['type'],sec['ordinal']['identifier']):
        #                print("found",sec['name'])
        #                return "<a href=\"/page/{}\">{}</a>".format(slugify(sec['name']),matchobj.group(1))
        #    print("using",matchobj.group(1))
        #    return "<a href=\"/page/{}\">{}</a>".format(slugify(matchobj.group(1)),matchobj.group(1))
    s = re.sub(r'{@(adventure|book) (.*?)\|(.*?)(\|(.*?))?(\|(.*?))?}', createALink, s)
#    def createBLink(matchobj):
#        return "<a href=\"/module/page/{}\">{}</a>".format(slugify(matchobj.group(1)),matchobj.group(1).title())
#    s = re.sub(r'{@book (.*?)\|(.*?)|.*?\|(.*?)}', createBLink, s)
    if '{@' in s:
        s = utils.remove5eShit(s)

    if re.search(r'{[@=](.*?)}',s):
        s = fixTags(s,d,p)
    return s


def idSearch(idno):
    def searchSection(sec,pageslug = None):
        if type(sec) == dict:
            if 'name' in sec:
                newslug = False
                for i in range(len(bookref["contents"])):
                    if 'ordinal' in bookref["contents"][i]:
                        sectitle = "{} {}: {}".format(bookref["contents"][i]['ordinal']['type'].title(),bookref["contents"][i]['ordinal']['identifier'],bookref["contents"][i]['name'])
                    else:
                        sectitle = "{}".format(bookref["contents"][i]['name'])
                    if re.match('(([Cc]h|[Aa]p).*: )?{}'.format(sec["name"]),sectitle):
                        pageslug = slugify(sectitle)
                        newslug = True
                    if 'headers' in bookref["contents"][i]:
                        for header in bookref["contents"][i]['headers']:
                            if type(header) == dict and header['header'] == sec["name"]:
                                pageslug = slugify(header['header'])
                                newslug = True
                                break;
                            elif str(header) == sec["name"]:
                                pageslug = slugify(header)
                                newslug = True
                                break;
                    if newslug:
                        break
            if args.manualbreak and 'name' in sec and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',sec['name']):
                pageslug = slugify(sec['name'])
            if 'id' in sec and sec["id"] == idno:
                return("/page/{}#{}".format(pageslug,idno))
            elif 'entries' in sec:
                return searchSection(sec["entries"],pageslug)
        elif type(sec) == list:
            for item in sec:
                path = searchSection(item,pageslug)
                if path:
                    return path
        else:
            return
    return searchSection(data['data'])

def markerSearch(page,marker):
    if len(marker) > 1:
        if marker[0] == '0':
            marker = 'O'+marker[1:]
        if page == "Island of Solstice":
            marker = 'I'+marker[1:]
        if page == "Holed Up":
            marker = 'L'+marker[1:]
        if re.match(r'^[A-Za-z]i$',marker):
            marker = marker[:1]+'1'
    if marker.startswith('Yi'):
        marker = 'Y1'+marker[2:]

    def searchSection(sec,pageslug = None,issec = False):
        if type(sec) == dict:
            if 'name' in sec:
                newslug = False
                for i in range(len(bookref["contents"])):
                    if 'ordinal' in bookref["contents"][i]:
                        sectitle = "{} {}: {}".format(bookref["contents"][i]['ordinal']['type'].title(),bookref["contents"][i]['ordinal']['identifier'],bookref["contents"][i]['name'])
                    else:
                        sectitle = "{}".format(bookref["contents"][i]['name'])
                    if re.match('(([Cc]h|[Aa]p).*: )?{}'.format(re.escape(sec["name"])),sectitle):
                        if re.match(r'((([Cc]h|[Aa]p).*:|The|A[n]?) )?{}'.format(page),sec["name"]):
                            issec = True
                        else:
                            issec = False
                        pageslug = slugify(sectitle)
                        newslug = True
                    if 'headers' in bookref["contents"][i]:
                        headermatch = False
                        for header in bookref["contents"][i]['headers']:
                            if type(header) == dict and header['header'] == sec["name"]:
                                if re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),header['header']) or \
                                        re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),sectitle) or \
                                        headermatch:
                                    issec = True
                                pageslug = slugify(header['header'])
                                newslug = True
                                break;
                            elif type(header) == str and str(header) == sec["name"]:
                                if re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),header) or \
                                        re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),sectitle):
                                    issec = True
                                pageslug = slugify(header)
                                newslug = True
                                break;
                            elif type(header) == str and re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),header):
                                headermatch = True
                            elif type(header) == str and "areas" not in header.lower():
                                headermatch = False
                    if newslug:
                        break
            if 'name' in sec and re.match(r'{}. {}'.format(re.escape(marker),re.escape(page)),sec['name']):
                issec = True
            if args.manualbreak and 'name' in sec and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',sec['name']):
                pageslug = slugify(sec['name'])
            #if 'name' in sec and re.match(r'^{}\.'.format(re.escape(marker)),sec["name"],re.IGNORECASE):
            #    print(marker,page,sec['name'],issec)
            if issec and 'name' in sec and re.match(r'^{}\.'.format(re.escape(marker)),sec["name"],re.IGNORECASE):
                label = sec["name"].split('.',2)[0] if marker.lower() == sec["name"].split('.',2)[0].lower() else marker.upper() if sec["name"].split('.',2)[0].isupper() else marker.lower()
                if 'id' in sec:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}#{}".format(pageslug,sec['id'])})
                else:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}".format(pageslug)})
            elif issec and 'name' in sec and re.match(r'^[0-9][a-zA-Z]$',re.escape(marker)) and \
                    re.match(r'{}(., )*?{}(, .)*?\.'.format(re.escape(marker[0]),re.escape(marker[1])),sec["name"],re.IGNORECASE):
                label = sec["name"].split('.',2)[0] if marker.lower() == sec["name"].split('.',2)[0].lower() else marker.upper() if sec["name"].split('.',2)[0].isupper() else marker.lower()
                if 'id' in sec:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}#{}".format(pageslug,sec['id'])})
                else:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}".format(pageslug)})    
            elif issec and 'name' in sec and \
                    re.match(r'([a-z0-9]+[-]{0}|{0}[-][a-z0-9]+)\.'.format(re.escape(marker)),sec["name"],re.IGNORECASE):
                label = sec["name"].split('.',2)[0] if marker.lower() == sec["name"].split('.',2)[0].lower() else marker.upper() if sec["name"].split('.',2)[0].isupper() else marker.lower()
                if 'id' in sec:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}#{}".format(pageslug,sec['id'])})
                else:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}".format(pageslug)})    
            elif issec and 'name' in sec and \
                    re.match(r'(.{{{0}}}, )*?{1}(, .{{{0}}})*?\.'.format(len(marker),re.escape(marker)),sec["name"],re.IGNORECASE):
                label = sec["name"].split('.',2)[0] if marker.lower() == sec["name"].split('.',2)[0].lower() else marker.upper() if sec["name"].split('.',2)[0].isupper() else marker.lower()
                if 'id' in sec:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}#{}".format(pageslug,sec['id'])})
                else:
                    return({"name": sec["name"],"label": label,"ref": "/page/{}".format(pageslug)})    
            elif 'entries' in sec:
                if 'name' in sec and re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),sec["name"]):
                    issec = True
                return searchSection(sec["entries"],pageslug,issec)
        elif type(sec) == list:
            if args.manualbreak:
                subsection = False
            for item in sec:
                if args.manualbreak and type(item) == dict and 'name' in item:
                    if re.match(r'((The|A[n]?) )?{}'.format(re.escape(page)),item['name']):
                        subsection = True
                    elif args.manualbreak and subsection and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',item['name']):
                        subsection = True
                    #else:
                    #    subsection = False
                    if subsection:
                        path = searchSection(item,pageslug,subsection)
                        if path:
                            return path
                path = searchSection(item,pageslug,issec)
                if path:
                    return path
        else:
            return
    return searchSection(data['data'])

def pageSearch(page):
    def searchSection(sec,pageslug = None,pagename = None):
        if type(sec) == dict:
            if 'name' in sec:
                newslug = False
                for i in range(len(bookref["contents"])):
                    if 'ordinal' in bookref["contents"][i]:
                        sectitle = "{} {}: {}".format(bookref["contents"][i]['ordinal']['type'].title(),bookref["contents"][i]['ordinal']['identifier'],bookref["contents"][i]['name'])
                    else:
                        sectitle = "{}".format(bookref["contents"][i]['name'])
                    if re.match('(([Cc]h|[Aa]p).*: )?{}'.format(re.escape(sec["name"])),sectitle):
                        pageslug = slugify(sectitle)
                        pagename = sec["name"]
                        newslug = True
                    if 'headers' in bookref["contents"][i]:
                        for header in bookref["contents"][i]['headers']:
                            if type(header) == dict and header['header'] == sec["name"]:
                                pageslug = slugify(header['header'])
                                pagename = sec["name"]
                                newslug = True
                                break;
                            elif str(header) == sec["name"]:
                                pageslug = slugify(header)
                                pagename = sec["name"]
                                newslug = True
                                break;
                    if newslug:
                        break

            if args.manualbreak and 'name' in sec and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',sec['name']):
                pageslug = slugify(sec['name'])
                pagename = sec["name"]
            if 'name' in sec and (re.match(r'((([Cc]h|[Aa]p).*:|The|A[n]?) )?{}'.format(re.escape(page)),sec["name"]) or \
                                    re.match(r'map ?[:-–—]? ?({})'.format(re.escape(page)),sec["name"],re.IGNORECASE)):
                if 'id' in sec:
                    return(("/page/{}#{}".format(pageslug,sec['id']),pagename,sec["name"]))
                else:
                    return(("/page/{}".format(pageslug),pagename,sec["name"]))
                
            elif 'title' in sec and (re.match(r'((([Cc]h|[Aa]p).*:|The|A[n]?) )?{}'.format(re.escape(page)),sec["title"]) or \
                                    re.match(r'map ?[:-–—]? ?({})'.format(re.escape(page)),sec["title"],re.IGNORECASE)):
                if 'id' in sec:
                    return(("/page/{}#{}".format(pageslug,sec['id']),pagename,sec["title"]))
                else:
                    return(("/page/{}".format(pageslug),pagename,sec["title"]))
            elif 'entries' in sec:
                return searchSection(sec["entries"],pageslug,pagename)
        elif type(sec) == list:
            for item in sec:
                path = searchSection(item,pageslug,pagename)
                if path and path != (None,None,None):
                    return path
        else:
            return
    return searchSection(data['data'])

def addLinkToMap(page,mapslug):
    def searchSection(sec,pageslug = None):
        if type(sec) == dict:
            if 'name' in sec:
                newslug = False
                for i in range(len(bookref["contents"])):
                    if 'ordinal' in bookref["contents"][i]:
                        sectitle = "{} {}: {}".format(bookref["contents"][i]['ordinal']['type'].title(),bookref["contents"][i]['ordinal']['identifier'],bookref["contents"][i]['name'])
                    else:
                        sectitle = "{}".format(bookref["contents"][i]['name'])
                    if re.match('(([Cc]h|[Aa]p).*: )?{}'.format(re.escape(sec["name"])),sectitle):
                        pageslug = slugify(sectitle)
                        newslug = True
                    if 'headers' in bookref["contents"][i]:
                        for header in bookref["contents"][i]['headers']:
                            if type(header) == dict and header['header'] == sec["name"]:
                                pageslug = slugify(header['header'])
                                newslug = True
                                break;
                            elif str(header) == sec["name"]:
                                pageslug = slugify(header)
                                newslug = True
                                break;
                    if newslug:
                        break
            if args.manualbreak and 'name' in sec and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',sec['name']):
                pageslug = slugify(sec['name'])
            if 'name' in sec and (re.match(r'((([Cc]h|[Aa]p).*:|The|A[n]?) )?{}'.format(re.escape(page)),sec["name"]) or \
                                re.match(r'map ?[:-–—]? ?({})'.format(re.escape(page)),sec["name"],re.IGNORECASE)) and 'id' in sec:
                content = module.find("./page[@id='{}']/content".format(str(uuid.uuid5(bookuuid,sec["id"]))))
                if content != None:
                    content.text = content.text.rstrip()+'\n<a href="/map/{}">Map: {}</a>\n'.format(mapslug,page)
            elif 'title' in sec and (re.match(r'((([Cc]h|[Aa]p).*:|The|A[n]?) )?{}'.format(re.escape(page)),sec["title"]) or \
                                re.match(r'map ?[:-–—]? ?({})'.format(re.escape(page)),sec["title"],re.IGNORECASE)) and 'id' in sec:
                content = module.find("./page[@id='{}']/content".format(str(uuid.uuid5(bookuuid,sec["id"]))))
                if content != None:
                    content.text = content.text.rstrip()+'\n<a href="/map/{}">Map: {}</a>\n'.format(mapslug,page)
            elif 'entries' in sec:
                return searchSection(sec["entries"],pageslug)
        elif type(sec) == list:
            for item in sec:
                path = searchSection(item,pageslug)
                if path:
                    return path
        else:
            return
    return searchSection(data['data'])

def processSection(order,d,mod,parentuuid=None,parentname=None):
    #global suborder
    suborder = 0
    if 'id' not in d:
        if 'name' not in d:
            d['name'] = parentname + "-child" + str(order)
        d['id'] = str(order)+d['name']
    sectionuuid = str(uuid.uuid5(bookuuid,d["id"]))
    d['currentpage'] = sectionuuid
    if book['id'].lower() == 'idrotf' and not parentuuid and d['name'] in [
            'Bremen','Bryn Shander','Caer-Dineval','Caer-Konig','Dougan\'s Hole',
            'Easthaven','Good Mead','Lonelywood','Targos','Termalaine'
            ]:
        parentuuid = str(uuid.uuid5(bookuuid,'040'))
        parentname = "Chapter 1: Ten-Towns"
        order += 3
    if parentuuid:
        page = ET.SubElement(module, 'page', { 'id': sectionuuid, 'parent': parentuuid, 'sort': str(order)})
    else:
        page = ET.SubElement(module, 'page', { 'id': sectionuuid, 'sort': str(order) })
    titlem = re.match(r'(Ch(\.|apter)|App(\.|endix)) [0-9A-B]+?:[ ]?(.*)', fixTags(d['name'],None,None,False,True))
    title = d['name']
    if not titlem and d['type'] == "section" and not parentuuid:
        for sec in bookref["contents"]:
            if sec['name'] == d['name'] and 'ordinal' in sec:
                title = "{} {}: {}".format(sec['ordinal']['type'].title(),sec['ordinal']['identifier'],sec['name'])
    name = ET.SubElement(page,'name')
    name.text = fixTags(title,None,None,False,True)
    d['pagetitle'] = title
    content = ET.SubElement(page,'content')
    d['content'] = content
    if parentuuid:
        content.text = "<h2 id=\"{}\">{}</h2>\n".format(d['id'],fixTags(d['name'],None,None,False,True))
    else:
        content.text = "<h1 id=\"{}\">{}</h1>\n".format(d['id'],fixTags(d['name'],None,None,False,True))
    slug = ET.SubElement(page,'slug')
    sectionslug = slugify(title)
    if sectionslug in slugs:
        sectionslug = slugify(title) + str(len([i for i in slugs if sectionslug in i]))
    slug.text = slugify(sectionslug)
    d['currentslug'] = sectionslug
    slugs.append(sectionslug)
    for e in d['entries']:
        issubsection = False
        if type(e) == dict:
            if 'type' not in e:
                e['type'] = 'entries'
            if e['type'] in ['entries','section'] and 'name' in e:
                chaptermatch = re.match(r'((Ch(\.|apter)|App(\.|endix)) ([0-9A-B]+?):[ ]?)(.*)',parentname if parentname else title)
                for sec in bookref["contents"]:
                    if chaptermatch and 'ordinal' in sec and sec['ordinal']['type'].lower() == chaptermatch.group(2).lower() and str(sec['ordinal']['identifier']).lower() == chaptermatch.group(5).lower():
                        chaptermatches = True
                    else:
                        chaptermatches = False
                    sectionregex = re.compile(r'((Ch(\.|apter)|App(\.|endix)) ([0-9A-B]+?):[ ]?)?{}'.format(re.escape(sec['name'])))
                    titlematch = sectionregex.match(parentname if parentname else title)
                    if titlematch or chaptermatches:
                        if 'headers' in sec:
                            for header in sec['headers']:
                                if (type(header) == dict and header["header"] == fixTags(e['name'],None,None,False,True)) or header == e['name']:
                                    issubsection = True
                if issubsection:
                    suborder += 1
                    subpage = processSection(suborder,e,mod,sectionuuid,title)
                    d['content'].text += "\n<a href=\"/page/{}\">{}</a>\n<br>\n".format(subpage,fixTags(e['name'],None,None,False,True))
                    d['subsection'] = str(uuid.uuid5(bookuuid,e["id"]))
                    d['subsectionname'] = fixTags(e['name'],None,None,False,True)
                    content = mod.find("./page[@id='{}']/content".format(d['subsection']))
                elif args.manualbreak and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',e['name']):
                    if 'subsection' not in d:
                        d['subsection'] = sectionuuid
                    if 'subsectionname' not in d:
                        d['subsectionname'] = title
                    issubsection = True
                    suborder += 1
                    subpage = processSection(suborder,e,mod,d['subsection'],d['subsectionname'])
                    #mod.find("./page[@id='{}']/content".format(d['subsection'])).text += "\n<a href=\"/page/{}\">{}</a>\n<br>\n".format(subpage,fixTags(e['name'],None,None,False,True))
                    #d['subsection'] = str(uuid.uuid5(bookuuid,e["id"]))
                    #d['subsectionname'] = fixTags(e['name'])
                    content = mod.find("./page[@id='{}']/content".format(d['subsection']))
                    if content.text.rfind("<br>\nUp: ") > 0:
                        content.text = content.text[:content.text.rindex("<br>\nUp: ")] + "\n<a href=\"/page/{}\">{}</a>\n<br>\n".format(subpage,fixTags(e['name'],None,None,False,True)) + content.text[content.text.rindex("<br>\nUp: "):]
                    else:
                        content.text += "\n<a href=\"/page/{}\">{}</a>\n<br>\n".format(subpage,fixTags(e['name'],None,None,False,True))

                if issubsection:
                    continue
                else:
                    content = d['content']
        if content.text.rfind("<br>\nUp: ") > 0:
            content.text = content.text[:content.text.rindex("<br>\nUp: ")] + getEntry(e,d) + content.text[content.text.rindex("<br>\nUp: "):]
        else:
            d['suborder'] = suborder
            content.text += getEntry(e,d)
    if parentname:
        d['content'].text += "<br>\nUp: <a href=\"/page/{}\">{}</a>\n<br>\n".format(parentuuid,parentname)
    content.text = content.text.rstrip()
    
    return slugify(sectionslug)

def getEntry(e,d=None,h=3,noencounter=False):
    if type(e) == dict:
        content = ""
        if e['type'] in ['entries','section'] and 'name' in e:
            issubsection = False
            chaptermatch = re.match(r'((Ch(\.|apter)|App(\.|endix)) ([0-9A-B]+?):[ ]?)(.*)',d['pagetitle'] if 'pagetitle' in d else e['name'])
            for sec in bookref["contents"]:
                suborder = 0
                if chaptermatch and 'ordinal' in sec and sec['ordinal']['type'].lower() == chaptermatch.group(2).lower() and str(sec['ordinal']['identifier']).lower() == chaptermatch.group(5).lower():
                    chaptermatches = True
                else:
                    chaptermatches = False
                sectionregex = re.compile(r'((Ch(\.|apter)|App(\.|endix)) ([0-9A-B]+?):[ ]?)?{}'.format(re.escape(sec['name'])))
                titlematch = sectionregex.match(d['pagetitle'] if 'pagetitle' in d else e['name'])
                if titlematch or chaptermatches:
                    if 'headers' in sec:
                        for header in sec['headers']:
                            suborder += 1
                            if (type(header) == dict and header["header"] == fixTags(e['name'],None,None,False,True)) or header == e['name']:
                                issubsection = True
                                break
                elif 'headers' in sec:
                    depth = 0
                    for header in sec['headers']:
                        suborder += 1
                        if type(header) == str and header == d['pagetitle']:
                            depth += 1
                        elif type(header) == str:
                            depth = 0
                        elif type(header) == dict and header['depth'] == depth and header['header'] == e['name']:
                            issubsection = True
                            break
                if issubsection:
                    break
            if args.manualbreak and not issubsection and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',e['name']):
                issubsection = True
            if issubsection:
                subpage = processSection(suborder,e,module,d['currentpage'],d['pagetitle'])
                content += "\n<a href=\"/page/{}\">{}</a>\n<br>\n".format(subpage,fixTags(e['name'],None,None,False,True))
                return content
                #d['subsection'] = str(uuid.uuid5(bookuuid,e["id"]))
                #d['subsectionname'] = fixTags(e['name'])
                #content = module.find("./page[@id='{}']/content".format(d['subsection'])).text
        if 'source' in e and e['source'].lower() != args.book:
            return ""
        if 'name' in e:
            if 'id' not in e:
                e['id'] = str(uuid.uuid5(bookuuid,e['name']))
            content += "<h{1} id=\"{2}\">{0}</h{1}>\n".format(e['name'],h,e['id'])
        if 'type' not in e and 'entries' in e:
            e['type'] = 'entries'
        if e['type'] == "list":
            content += "<ul>\n"
            for i in e['items']:
                content += "<li>{}</li>".format(getEntry(i,d,h,noencounter))
            content += "</ul>\n"
            return content
        elif e['type'] == "entries" or e['type'] == "section":
            content += getEntry(e['entries'],d,4,noencounter)
            return content
        elif e['type'] == "patron" or e['type'] == "options" or e['type'] == "optfeature":
            if 'prerequisite' in e and type(e['entries'][0]) == str:
                e['entries'][0] = "<i>Prerequisite: {}</i><br>{}".format(e['prerequisite'],e['entries'][0])
            elif 'prerequisite' in e:
                e['entries'].insert(0,"<i>Prerequisite: {}</i><br>".format(e['prerequisite']))
            if 'name' in e and type(e['entries'][0]) == str:
                e['entries'][0] = "<b>{}</b><br>{}".format(e['name'],e['entries'][0])
            elif 'name' in e:
                e['entries'].insert(0,"<b>{}</b><br>".format(e['name']))
            return getEntry(e['entries'],d,h,noenocunter)
        elif e['type'] == "table":
            return getTable(e,d)
        elif e['type'] == "inset":
            content += "<blockquote>\n"
            if 'name' in e:
                content += "<h4 id=\"{}\">{}</h4>\n".format(e['id'],e['name'])
            for x in e['entries']:
                content += getEntry(x,d,h,noencounter)
            content += "</blockquote>\n"
            return content
        elif e['type'] == "item":
            return "<b>{}</b> {}".format(e['name'],fixTags(e['entry'] if 'entry' in e else getEntry(e['entries'],d,h,noencounter),d,e,noencounter))
        elif e['type'] == "tableGroup":
            for table in e['tables']:
                content += getTable(table,d)
            return content
        elif e['type'] == "link":
            return "<a href=\"{}\">{}</a>".format(e['href']['path'],e['text'])
        elif e['type'] == "abilityGeneric":
            return "<p class=\"text-center\">{}</p>\n".format(fixTags(e['text'],d,e,noencounter))
        elif e['type'] == "abilityDc":
            return "<p class=\"text-center\"><b>{} save DC</b> = 8 + your proficiency bonus + your {} modifier</p>\n".format(e['name']," modifier + your ".join([stats[x] for x in e["attributes"]]))
        elif e['type'] == "abilityAttackMod":
            return "<p class=\"text-center\"><b>{} attack modifier</b> = your proficiency bonus + your {} modifier</p>\n".format(e['name']," modifier + your ".join([stats[x] for x in e["attributes"]]))
        elif e['type'] == 'image':
            content += "<p>\n"
            shutil.copy("./img/" + e['href']['path'],os.path.join(tempdir,os.path.basename(e['href']['path'])))
            #with Image(filename="./img/" + e['href']['path']) as img:
            #    if img.width > 8192 or img.height > 8192:
            #        img.transform(resize='8192x8192>')
            #    img.save(filename=os.path.join(tempdir,os.path.basename(e['href']['path'])))
            content += "<img src=\"{}\"><br>\n".format(os.path.basename(e['href']['path']))
            if 'title' in e:
#                if 'map' in e['title'].lower():
#                    maptitle = e['title']
#                    mapbaseslug = d['currentslug'] + "-map"
#                    mapslug = mapbaseslug + str(len([i for i in slugs if mapbaseslug in i]))
#                    mapuuid = str(uuid.uuid5(bookuuid,mapslug))
#                    slugs.append(mapslug)
#                    mapentry = ET.SubElement(module,'map',{'id': mapuuid,'parent': d['subsection'] if 'subsection' in d else d['currentpage'],'sort': str(len([i for i in slugs if mapbaseslug in i]) + 199)})
#                    ET.SubElement(mapentry,'name').text = maptitle
#                    ET.SubElement(mapentry,'slug').text = mapslug
#                    ET.SubElement(mapentry,'image').text = os.path.basename(e['href']['path'])
#                    content += '<a href="/map/{}"><i>{}</i></a><br>\n'.format(mapslug,e['title'])
#                else:
                    content += "<i>{}</i><br>\n".format(e['title'])
            content += "</p>\n"
            return content
        elif e['type'] == 'inline':
            content += "<p>\n"
            content += " ".join([re.sub(r'</?p>','',getEntry(x,d,h,noencounter)) for x in e['entries']])
            content += "</p>\n"
            return content
        elif e['type'] == 'inlineBlock':
            content += "<blockquote>\n"
            content += "<p>\n"
            content += " ".join([re.sub(r'</?p>','',getEntry(x,d,h,noencounter)) for x in e['entries']])
            content += "</p>\n"
            content += "</blockquote>\n"
            return content
        elif e['type'] == 'cell':
            if 'exact' in e['roll']:
                return "{}".format(e['roll']['exact'])
            elif 'min' in e['roll'] and 'max' in e['roll']:
                return "{}-{}".format(e['roll']['min'],e['roll']['max'])
        elif e['type'] == 'quote':
            if 'by' in e:
                return "<p><i>{}</i></p><span class=\"text-right\">&mdash;{}<i>{}</i></span>".format("<br>".join(e['entries']),e['by'],', '+e['from'] if 'from' in e else '')
            else:
                return "<p><i>{}</i></p>".format("<br>".join(e['entries']))
        elif e['type'] == 'insetReadaloud':
            content += "<blockquote class=\"read\">\n"
            for x in e['entries']:
                content += "<p>{}</p>\n".format(fixTags(getEntry(x,d,h,noencounter),d,e,noencounter))
            content += "</blockquote>\n"
            return content
        elif e['type'] == 'gallery':
            content += "<p>"
            for image in e['images']:
                content += "<img src=\"{}\"><br>\n".format(os.path.basename(image['href']['path']))
                #maptitle = ""
                if 'title' in image:
                #    if "player version" in image['title'].lower() or 'map' in image['title'].lower():
                #        if image['title'] == "(Player Version)":
                #            maptitle += " " + image['title']
                #        else:
                #            maptitle = image['title']
                #        mapbaseslug = d['currentslug'] + "-map"
                #        mapslug = mapbaseslug + str(len([i for i in slugs if mapbaseslug in i]))
                #        mapuuid = str(uuid.uuid5(bookuuid,mapslug))
                #        slugs.append(mapslug)
                #        mapentry = ET.SubElement(module,'map',{'id': mapuuid,'parent': d['subsection'] if 'subsection' in d else d['currentpage'],'sort': str(len([i for i in slugs if mapbaseslug in i]) + 199)})
                #        ET.SubElement(mapentry,'name').text = maptitle
                #        ET.SubElement(mapentry,'slug').text = mapslug
                #        ET.SubElement(mapentry,'image').text = os.path.basename(image['href']['path'])
                #        content += '<a href="/map/{}"><i>{}</i></a><br>\n'.format(mapslug,image['title'])
                #    else:
                        content += "<i>{}</i><br>\n".format(image['title'])
                shutil.copy("./img/" + image['href']['path'],os.path.join(tempdir,os.path.basename(image['href']['path'])))
                #with Image(filename="./img/" + image['href']['path']) as img:
                #    if img.width > 8192 or img.height > 8192:
                #        img.transform(resize='8192x8192>')
                #    img.save(filename=os.path.join(tempdir,os.path.basename(image['href']['path'])))
            content += "</p>\n"
            return content
        elif e['type'] == 'flowchart':
            line = '<div style="font-size: 0; width: 3px; height: 20px; color: #cdb078; background-color: #cdb078; margin: auto"></div>'
            return '<div align="center">{}</div>'.format(line.join([getEntry(x,d,h,True) for x in e['blocks']]))
        elif e['type'] == 'flowBlock':
            borderimg = "url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAADAAAAAwAgMAAAAqbBEUAAAABGdBTUEAALGPC/xhBQAAAAFzUkdCAK7OHOkAAAAJUExURQAAAP///82weFCq0dQAAAABdFJOUwBA5thmAAAAMUlEQVQoz2NgYGDQWgUEKxggAA8nFAgGjgNyCogDovFwVobCQdZw4BDp7YGPH+ISEgAPpq39iSHY4QAAAABJRU5ErkJggg==')"
            content = '<div style="text-align:left;border: 16px solid transparent;border-image-slice: 16 16 16 16 fill;border-image-source: {}">'.format(borderimg)
            if 'name' in e:
                content += '<h4 align="center">{}</h4>\n'.format(e['name'])
            content += "\n".join([getEntry(x,d,h) for x in e['entries']])
            content += "</div>"
            return content
        else:
            print("Dont know",e['type'])
            print(e)
            return "UNKNOWN"
    elif type(e) == list:
        itemlist = []
        for i in e:
            itemlist.append(getEntry(i,d,h,noencounter))
        return "\n".join(itemlist)
    elif e == "":
        return " &nbsp; "
    else:
        return "<p>{}</p>".format(fixTags(str(e),d,e,noencounter))

def getTable(e,d=None):
    content = "<table>\n"
    if 'caption' in e:
        content += "<caption>{}</caption>\n".format(fixTags(e['caption']))
    if 'colLabels' in e:
        content += "<thead><tr>\n"
        for i in range(len(e['colLabels'])):
            content += "<td class=\"{}\">{}</td>".format(e['colStyles'][i] if 'colStyles' in e else '',fixTags(e['colLabels'][i],d,e,True))
        content += "</thead></tr>\n"
    content += "<tbody>\n"
    for row in e['rows']:
        if type(row) == dict:
            content += "<tr class=\"{}\">\n".format(row['style'])
            for rc in row['row']:
                content += "<td>{}</td>\n".format(getEntry(rc,d,3,True))
        else:
            content += "<tr>\n"
            for rc in row:
                content += "<td>{}</td>\n".format(getEntry(rc,d,3,True))
        content += "</tr>\n"
    content += "</tbody>\n"
    content += "</table>\n"
    return content

def createMap(map,mapgroup):
    if 'attributes' in map:
        map["name"] = map["attributes"]["name"]
        bgimg = None
        map["width"] = 0
        map["height"] = 0
        for image in map["graphics"]:
            if image["layer"] != "map":
                continue
            if type(image["width"]) == str:
                image["width"] = float(image["width"])
            if type(image["height"]) == str:
                image["height"] = float(image["height"])
            if image["width"] > map["width"] or image["height"] > map["height"]:
                map["width"] = image["width"]
                map["height"] = image["height"]
                bgimg = image
        if not bgimg:
            return
        map["width"] = map["attributes"]["width"]*70
        map["height"] = map["attributes"]["height"]*70
        map["sort"] = map['attributes']['placement']
        map["grid"] = round(map['attributes']['snapping_increment']*(map['attributes']['scale_number']/5)/map['attributes']['scale_number']*350)
        map["gridDistance"] = round(map['attributes']['scale_number'])
        map["gridUnits"] = map['attributes']['scale_units']
        map["gridAlpha"] = 1 if map['attributes']['showgrid'] else 0
        map["gridColor"] = map['attributes']['gridcolor']
        if not os.path.exists("./img/roll20/{}".format(book["id"])):
            os.mkdir("./img/roll20/{}".format(book["id"]))
        imgext = os.path.splitext(os.path.basename(urllib.parse.urlparse(bgimg["imgsrc"]).path))[1]
        if not imgext:
            imgext = ".png"
        if not os.path.exists("./img/roll20/{}/map{}{}".format(book["id"],bgimg["id"],imgext)):
            imagesrc = re.sub(r'(med.|thumb.)', 'original.',bgimg["imgsrc"])
            req = urllib.request.Request(imagesrc, headers={'user-agent': 'mozilla/5.0'})
            try:
                imgfile = urllib.request.urlopen(req)
                with Image(file=imgfile) as img:
                    if bgimg["rotation"] != 0:
                        img.rotate(bgimg["rotation"])
                    img.save(filename="./img/roll20/{}/map{}{}".format(book["id"],bgimg["id"],imgext))
            except urllib.error.HTTPError as e:
                print(" |> Map Error {}: {} {}".format(e.code,bgimg["id"],imagesrc),file=sys.stderr,end='')
                return
        map["img"] = "./img/roll20/{}/map{}{}".format(book["id"],bgimg["id"],imgext)
        map["shiftX"] = (bgimg["width"]/2.0) - bgimg["left"]
        map["shiftY"] = (bgimg["height"]/2.0) - bgimg["top"]
    else:
        map["offsetX"] = (map["width"] + math.ceil(0.5 * map["width"] / (map["grid"] * 2)) * (map["grid"] * 2) - map["width"]) * 0.5
        map["offsetY"] = (map["height"] + math.ceil(0.5 * map["height"] / (map["grid"] * 2)) * (map["grid"] * 2) - map["height"]) * 0.5

    if map["name"] == "Start":
        return
    if map["name"] == "Upper Courtyard - Skyreach Caste":
        map["name"] = "Upper Courtyard - Skyreach Castle"
    if map["name"] == "Sacred Stone Monastary":
        map["name"] = "Sacred Stone Monastery"
    mapbaseslug = slugify(map['name'])
    mapslug = mapbaseslug + str(len([i for i in slugs if mapbaseslug in i]))
    mapuuid = uuid.uuid5(bookuuid,mapslug)
    parent = mapgroup
    slugs.append(mapslug)
    if not map["img"] and map["tiles"][0]["width"] >= map["width"] and map["tiles"][0]["height"] >= map["height"]:
        bg = map["tiles"].pop(0)
        if bg["img"].startswith("worlds/"):
            bg["img"] = "./data/" + bg["img"]
        imgext = os.path.splitext(os.path.basename(urllib.parse.urlparse(bg["img"]).path))[1]
        if not imgext:
            imgext = ".png"
        if imgext == ".webp":
            PIL.Image.open(bg["img"]).save(os.path.join(tempdir,os.path.basename("map-{}.png".format(mapslug))))
            map["img"] = os.path.join(tempdir,os.path.basename("map-{}.png".format(mapslug)))
        else:
            map["img"] = shutil.copy(bg["img"],os.path.join(tempdir,os.path.basename("map-{}{}".format(mapslug,imgext))))
        map["shiftX"] = bg["x"]-map["offsetX"]
        map["shiftY"] = bg["y"]-map["offsetY"]
        map["width"] = bg["width"]
        map["height"] = bg["height"]
    map["rescale"] = 1.0
    if map["width"] > 8192 or map["height"] > 8192:
        map["rescale"] = 8192.0/map["width"] if map["width"] >= map["height"] else 8192.0/map["height"]
        map["grid"] = round(map["grid"]*map["rescale"])
        map["width"] *= map["rescale"]
        map["height"] *= map["rescale"]
        map['shiftX'] *= map["rescale"]
        map['shiftY'] *= map["rescale"]

    mapentry = ET.SubElement(module,'map',{'id': str(mapuuid),'parent': mapgroup,'sort': str(map["sort"])})
    ET.SubElement(mapentry,'name').text = map['name']
    ET.SubElement(mapentry,'slug').text = mapslug
    ET.SubElement(mapentry,'gridSize').text = str(round(map["grid"]))#*(5.0/map["gridDistance"])))
    ET.SubElement(mapentry,'gridScale').text = str(round(map["gridDistance"]))#*((5.0/map["gridDistance"]))))
    ET.SubElement(mapentry,'gridUnits').text = str(map["gridUnits"])
    ET.SubElement(mapentry,'gridVisible').text = "YES" if map['gridAlpha'] > 0 else "NO"
    ET.SubElement(mapentry,'gridColor').text = map['gridColor']
    ET.SubElement(mapentry,'gridOffsetX').text = str(round(map['shiftX']))
    ET.SubElement(mapentry,'gridOffsetY').text = str(round(map['shiftY']))

    if map["img"]:
        if map["img"].startswith("worlds/"):
            map["img"] = "./data/" + map["img"]
        imgext = os.path.splitext(os.path.basename(map["img"]))[1]
        if imgext == ".webp":
            ET.SubElement(mapentry,'image').text = os.path.splitext(os.path.basename(map["img"]))[0]+".png"
        else:
            ET.SubElement(mapentry,'image').text = os.path.basename(map["img"])
        with Image(filename=map["img"]) as img:
            if img.width > 8192 or img.height > 8192:
                img.transform(resize='8192x8192>')
                if imgext == ".webp":
                    img.save(filename=os.path.join(tempdir,os.path.splitext(os.path.basename(map["img"]))[0]+".png"))
                else:
                    img.save(filename=os.path.join(tempdir,os.path.basename(map["img"])))
            elif not os.path.exists(os.path.join(tempdir,os.path.basename(map["img"]))):
                if imgext == ".webp":
                    img.save(filename=os.path.join(tempdir,os.path.splitext(os.path.basename(map["img"]))[0]+".png"))
                else:
                    shutil.copy(map["img"],os.path.join(tempdir,os.path.basename(map["img"])))
            if map["height"] != img.height or map["width"] != img.width:
                map["scale"] = map["width"]/img.width if map["width"]/img.width >= map["height"]/img.height else map["height"]/img.height
            else:
                map["scale"] = 1.0
    else:
        print(" |> Map Error NO BG FOR: {}".format(map["name"]),file=sys.stderr,end='')
        with Image(filename="./data/worlds/nobg.png") as img:
            img.transform(resize='{}x{}!'.format(map["width"],map["height"]))
            img.save(filename=os.path.join(tempdir,"automap-{}.png".format(mapslug)))
        ET.SubElement(mapentry,'image').text = os.path.basename("automap-{}.png".format(mapslug))
        map["scale"] = 1.0
        if 'thumb' in map and map["thumb"]:
            if map["thumb"].startswith("worlds/"):
                map["thumb"] = "./data/" + map["thumb"]
            imgext = os.path.splitext(os.path.basename(map["img"]))[1]
            if imgext == ".webp":
                ET.SubElement(mapentry,'snapshot').text = "thumb-"+os.path.splitext(os.path.basename(map["thumb"]))[0]+".png"
                PIL.Image.open(map["thumb"]).save(os.path.join(tempdir,"thumb-"+os.path.splitext(os.path.basename(map["img"]))[0]+".png"))
            else:
                ET.SubElement(mapentry,'snapshot').text = "thumb-"+os.path.basename(map["thumb"])
                shutil.copy(map["thumb"],os.path.join(tempdir,"thumb-"+os.path.basename(map["thumb"])))

    ET.SubElement(mapentry,'scale').text = str(map["scale"])
    if "paths" in map:
        map["walls"] = map["paths"]
    if "walls" in map and len(map["walls"])>0:
        ET.SubElement(mapentry,'lineOfSight').text = "YES"
        ET.SubElement(mapentry,'canvas').text = mapslug + ".svg"
        svguuid = str(uuid.uuid5(mapuuid,"svg"))
        svg = ET.Element('svg', { 'id': svguuid, 'xmlns': 'http://www.w3.org/2000/svg', 'version': '1.0', 'viewBox': "0 0 {} {}".format(map['width'],map['height']) } )
        for i in range(len(map["walls"])):
            p = map["walls"][i]
            print("\rwall {}".format(i),file=sys.stderr,end='')
            if 'path' in p:
                rawpath = json.loads(p['path'])
                path = ""
                pathlist = []
                for i in range(len(rawpath)):
                    path += rawpath[i][0]
                    if rawpath[i][0] in ['M','L']:
                        pathlist.append(rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)
                        path += "{},{}".format(
                                (rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"]
                                )
                    elif rawpath[i][0] in ['C']:
                        pathlist.append(rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)
                        pathlist.append(rawpath[i][3]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][4]+p["top"]+map['shiftY']-p['height']/2)
                        pathlist.append(rawpath[i][5]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][6]+p["top"]+map['shiftY']-p['height']/2)
                        path += "{},{},{},{},{},{}".format(
                                (rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"],
                                (rawpath[i][3]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][4]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"],
                                (rawpath[i][5]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][6]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"]
                                )
                    elif rawpath[i][0] in ['Q']:
                        pathlist.append(rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)
                        pathlist.append(rawpath[i][3]+p["left"]+map['shiftX']-p['width']/2)
                        pathlist.append(rawpath[i][4]+p["top"]+map['shiftY']-p['height']/2)
                        path += "{},{},{},{}".format(
                                (rawpath[i][1]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][2]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"],
                                (rawpath[i][3]+p["left"]+map['shiftX']-p['width']/2)*map["rescale"],
                                (rawpath[i][4]+p["top"]+map['shiftY']-p['height']/2)*map["rescale"]
                                )
            else:
                pathlist = [
                        (p["c"][0]-map["offsetX"])*map["rescale"],
                        (p["c"][1]-map["offsetY"])*map["rescale"],
                        (p["c"][2]-map["offsetX"])*map["rescale"],
                        (p["c"][3]-map["offsetY"])*map["rescale"]
                        ]
                path = "M{},{}L{},{}".format(*pathlist)
            isConnected = False
            for pWall in mapentry.iter('wall'):
                lastpath = pWall.find('data')
                pWallID=pWall.get('id')
                if lastpath != None and lastpath.text.endswith(",{:.1f},{:.1f}".format(pathlist[0],pathlist[1])):
                    wType = pWall.find('type')
                    if p['door'] > 0:
                        if p['door'] == 1 and wType.text != 'door':
                            continue
                        if p['door'] == 2 and wType.text != 'secretDoor':
                            continue
                        if p['ds'] > 0:
                            door = pWall.find('door')
                            if door == None:
                                continue
                            elif p['ds'] == 1 and door.text != 'open':
                                continue
                            elif p['ds'] == 2 and door.text != 'locked':
                                continue
                    elif p['move'] == 0 and p['sense'] == 1 and wType.text != 'ethereal':
                        continue
                    elif p['move'] == 1 and p['sense'] == 0 and wType.text != 'invisible':
                        continue
                    elif p['move'] == 1 and p['sense'] == 2 and wType.text != 'terrain':
                        continue
                    if 'dir' in p:
                        wSide = pWall.find('side')
                        if wSide == None and p['dir'] > 0:
                            continue
                        if p['dir'] == 1 and wSide.text != 'left':
                            continue
                        if p['dir'] == 1 and wSide.text != 'right':
                            continue
                    isConnected = True
                    pWall.set('id',pWallID+' '+p['_id'])
                    lastpath.text += ','+','.join("{:.1f}".format(x) for x in pathlist)
                    break
            if not isConnected:
                wall = ET.SubElement(mapentry,'wall',{'id': p['id'] if 'id' in p else p['_id'] })
                lastpath = ET.SubElement(wall,'data')
                lastpath.text = ','.join("{:.1f}".format(x) for x in pathlist)
            if not isConnected:
                if 'stroke' in p:
                    if p["stroke"] == 'transparent':
                        ET.SubElement(wall,'color').text = '#ff00ff'
                        ET.SubElement(wall,'type').text = 'invisible'
                    else:
                        ET.SubElement(wall,'color').text = p["stroke"]
                        ET.SubElement(wall,'type').text = 'door' if p["stroke"] == '#ff9900' else 'normal'
                else:
                    if 'door' in p and p['door'] == 1:
                        ET.SubElement(wall,'type').text = 'door'
                        ET.SubElement(wall,'color').text = '#00ffff'
                        if p['ds'] > 0:
                            ET.SubElement(wall,'door').text = 'locked' if p['ds'] == 2 else 'open'
                    elif p['door'] == 2:
                        ET.SubElement(wall,'type').text = 'secretDoor'
                        ET.SubElement(wall,'color').text = '#00ffff'
                        if p['ds'] > 0:
                            ET.SubElement(wall,'door').text = 'locked' if p['ds'] == 2 else 'open'
                    elif p['move'] == 0 and p['sense'] == 1:
                        ET.SubElement(wall,'type').text = 'ethereal'
                        ET.SubElement(wall,'color').text = '#7f007f'
                    elif p['move'] == 1 and p['sense'] == 0:
                        ET.SubElement(wall,'type').text = 'invisible'
                        ET.SubElement(wall,'color').text = '#ff00ff'
                    elif p['move'] == 1 and p['sense'] == 2:
                        ET.SubElement(wall,'type').text = 'terrain'
                        ET.SubElement(wall,'color').text = '#ffff00'
                    else:
                        ET.SubElement(wall,'type').text = 'normal'
                        ET.SubElement(wall,'color').text = '#ff7f00'
                    if 'dir' in p and p['dir'] > 0:
                        ET.SubElement(wall,'side').text = 'left' if p['dir'] == 2 else 'right'

                    if 'door' in p and p['door'] > 0:
                        p["stroke"] = '#00ffff'
                    else:
                        p["stroke"] = '#ff7f00'
                    p["stroke_width"] = 5
                    p["layer"] = "walls"

                ET.SubElement(wall,'generated').text = 'YES'

                ET.SubElement(svg,'path', {
                    'class' : "wall" if p["layer"] == "walls" else p["layer"],
                    'stroke': '#00ffff' if p["stroke"] == '#ff9900' else '#ff7f00',
                    'stroke-opacity': "1.0",
                    'stroke-width': str(p["stroke_width"]),
                    'stroke-linejoin': "round",
                    'stroke-linecap': "round",
                    'fill': "none",
                    'd': path } )

        tree = ET.ElementTree(utils.indent(svg, 1))
        tree.write(os.path.join(tempdir,mapslug + ".svg"), xml_declaration=False, short_empty_elements=False, encoding='utf-8')

    maptitle = map["name"]
    mapname = map["name"]
    floor = ''
    markerprefix = ''
    if ' - ' in map["name"]:
        floor = map["name"].split(' - ',2)[0]
        if re.match(r'(ground|first)',floor.lower()):
            floor = '1'
        elif re.match(r'(second)',floor.lower()):
            floor = '2'
        elif re.match(r'(third)',floor.lower()):
            floor = '3'
        else:
            floor = ''
    mapexceptions = {
        'hotdq': [
            { 'name': "Dungeon  - Castle Naerytar",
                'maptitle': "Beneath the Castle" },
            ],
        'rot': [
            { 'name': "Well of Dragons Caldera",
                'maptitle': "Well of Dragons" },
            { 'name': "Well of Dragons Temple",
                'maptitle': "Tiamat's Temple" },
            { 'name': "Tomb of Diderius",
                'mapname': "Chapters 11 and 12: Death to the Wyrmspeakers" },
            { 'name': "Arauthator's Lair",
                'mapname': "Chapter 10: The Sea of Moving Ice" }
            ],
        'pota': [
            { 'name': "Shrine of the Tender Oath",
                'mapname': "Vale of Dancing Waters" },
            { 'name': "Scarlet Moon Hall Tower",
                'maptitle': "Scarlet Moon Hall" }
            ],
        'cos': [
            { 'name': re.compile(r'.*(Ravenloft).*'),
                'maptitle': "Castle Ravenloft",
                'prefix': 'K' },
            { 'name': "Death House - Dungeon",
                'maptitle': "Death House" },
            { 'name': re.compile(r'.*(Amber Temple).*'),
                'maptitle': "The Amber Temple" },
            { 'name': "Barovia",
                'maptitle': "The Lands of Barovia" },
            { 'name': re.compile(r'.*(Abbey of Saint Markovia).*'),
                'maptitle': "Abbey of Saint Markovia" },
            { 'name': re.compile(r'.*(Argynvostholt).*'),
                'maptitle': "Argynvostholt" },
            { 'name': "Town of Vallaki",
                'maptitle': "The Town of Vallaki" }
            ],
        'skt': [
            ],
        'oota': [
            { 'name': "The Hook Horror Lair",
                'maptitle': 'Hook Horror Hunt' },
            { 'name': "Whorlstone 7 & 8: Gray Ghost Garden & Gray Alchemist",
                'mapname': 'Whorlstone Tunnels' },
            { 'name': "The Lost Tomb",
                'maptitle': 'Lost Tomb of Khaem' },
            ],
        'idrotf': [
            { 'name': "Caer Dineval",
                'maptitle': 'Caer-Dineval' },
            { 'name': "Caer Konig",
                'maptitle': 'Caer-Konig' },
            { 'name': "Keep at Caer-Dineval",
                'maptitle': 'Black Swords' },
            { 'name': "Duergar Outpost",
                'maptitle': 'The Unseen' },
            { 'name': "Frost Giant Ice Lodge",
                'maptitle': 'Holed Up' },
            { 'name': "Cauldron Caves",
                'mapname': "Toil and Trouble" },
            { 'name': "Verbeeg Lair",
                'mapname': "The Mead Must Flow" },
            { 'name': "Kelvin's Cairn",
                'mapname': "Mountain Climb" },
            { 'name': "Gem Mine",
                'mapname': "A Beautiful Mine" }
            ]
        }
    if book["id"].lower() in mapexceptions.keys():
        for ex in mapexceptions[book['id'].lower()]:
            if (type(ex['name']) == re.Pattern and ex['name'].match(map['name'])) or ex['name'] == map['name']:
                maptitle = ex['maptitle'] if 'maptitle' in ex else map["name"]
                mapname = ex['mapname'] if 'mapname' in ex else maptitle
                markerprefix = ex['prefix'] if 'prefix' in ex else None
    (pageref,altmapname,mapsection) = pageSearch(maptitle) or (None,None,None)
    #print(map["name"],"(",maptitle,") ->",pageref,altmapname,mapsection)
    if pageref:
        marker = ET.SubElement(mapentry,'marker')
        ET.SubElement(marker,'name').text = maptitle
        ET.SubElement(marker,'label').text = "Info"
        ET.SubElement(marker,'color').text = '#ff0000'
        ET.SubElement(marker,'shape').text = 'marker'
        ET.SubElement(marker,'size').text = 'medium' if map['scale'] < 1.1 else 'large' if map['scale'] < 1.2 else 'huge'
        ET.SubElement(marker,'hidden').text = 'YES'
        ET.SubElement(marker,'locked').text = 'YES'
        ET.SubElement(marker,'x').text = str(round(map["width"]*.1))
        ET.SubElement(marker,'y').text = str(round(map["height"]*.1))
        ET.SubElement(marker,'content',{ 'ref': pageref })
        addLinkToMap(map["name"],mapslug)
    elif ' - ' in mapname:
        (pageref,altmapname,mapsection) = pageSearch(maptitle.split(' - ',2)[1]) or (None,None,None)
        if pageref:
            if mapname == maptitle:
                mapname = maptitle.split(' - ',2)[1]
            maptitle = maptitle.split(' - ',2)[1]
            marker = ET.SubElement(mapentry,'marker')
            ET.SubElement(marker,'name').text = maptitle
            ET.SubElement(marker,'label').text = "Info"
            ET.SubElement(marker,'color').text = '#ff0000'
            ET.SubElement(marker,'shape').text = 'marker'
            ET.SubElement(marker,'size').text = 'medium' if map['scale'] < 1.1 else 'large' if map['scale'] < 1.2 else 'huge'
            ET.SubElement(marker,'hidden').text = 'YES'
            ET.SubElement(marker,'locked').text = 'YES'
            ET.SubElement(marker,'x').text = str(round(map["width"]*.1))
            ET.SubElement(marker,'y').text = str(round(map["height"]*.1))
            ET.SubElement(marker,'content',{ 'ref': pageref })
            addLinkToMap(map["name"],mapslug)
        else:
            (pageref,altmapname,mapsection) = pageSearch(maptitle.split(' - ',2)[0]) or (None,None,None)
            if pageref:
                if mapname == maptitle:
                    mapname = maptitle.split(' - ',2)[0]
                maptitle = maptitle.split(' - ',2)[0]
                marker = ET.SubElement(mapentry,'marker')
                ET.SubElement(marker,'name').text = maptitle
                ET.SubElement(marker,'label').text = "Info"
                ET.SubElement(marker,'color').text = '#ff0000'
                ET.SubElement(marker,'shape').text = 'marker'
                ET.SubElement(marker,'size').text = 'medium' if map['scale'] < 1.1 else 'large' if map['scale'] < 1.2 else 'huge'
                ET.SubElement(marker,'hidden').text = 'YES'
                ET.SubElement(marker,'locked').text = 'YES'
                ET.SubElement(marker,'x').text = str(round(map["width"]*.1))
                ET.SubElement(marker,'y').text = str(round(map["height"]*.1))
                ET.SubElement(marker,'content',{ 'ref': pageref })
                addLinkToMap(map["name"],mapslug)
    if not altmapname:
        altmapname = mapname
    if mapsection and not floor:
        sectionarea = re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',altmapname)
        if sectionarea:
            markerprefix = sectionarea.group(1)
    if markerprefix:
        floor = markerprefix + floor

    if 'graphics' in map:
        for i in range(len(map["graphics"])):
            image = map["graphics"][i]
            print("\rassets [{}/{}]".format(i,len(map["graphics"])),file=sys.stderr,end='')
            if image["id"] == bgimg["id"] or image["represents"] != "":
                continue
            tile = ET.SubElement(mapentry,'tile')
            ET.SubElement(tile,'x').text = str(round(image["left"]*map["rescale"]))
            ET.SubElement(tile,'y').text = str(round(image["top"]*map["rescale"]))
            ET.SubElement(tile,'width').text = str(round(image["width"]*map["rescale"]))
            ET.SubElement(tile,'height').text = str(round(image["height"]*map["rescale"]))
            ET.SubElement(tile,'opacity').text = "1.0"
            ET.SubElement(tile,'locked').text = "YES"
            ET.SubElement(tile,'layer').text = "dm" if image["layer"] == 'gmlayer' else "object"

            if image["light_radius"]:
                if type(image["light_dimradius"]) == str:
                    image["light_dimradius"] = float(image["light_dimradius"] or 0)
                if type(image["light_radius"]) == str:
                    image["light_radius"] = float(image["light_radius"] or 0)
                light = ET.SubElement(tile,'light')
                ET.SubElement(light,'enabled').text = "YES"
                ET.SubElement(light,'radiusMin').text = str(round(image["light_dimradius"]))
                ET.SubElement(light,'radiusMax').text = str(round(image["light_radius"]))
                ET.SubElement(light,'alwaysVisible').text = "NO"
                ET.SubElement(light,'color').text = "#ffffff"
                ET.SubElement(light,'opacity').text = "0.5"

            asset = ET.SubElement(tile,'asset')
            ET.SubElement(asset,'name').text = image["name"] or "Map Asset {:03d}".format(i)
            ET.SubElement(asset,'type').text = "image"

            imgext = os.path.splitext(os.path.basename(urllib.parse.urlparse(image["imgsrc"]).path))[1]
            if not imgext:
                imgext = ".png"
            ET.SubElement(asset,'resource').text = "asset{}{}".format(image["id"],imgext)
            if not os.path.exists("./img/roll20/{}/asset{}{}".format(book["id"],image["id"],imgext)):
                imagesrc = re.sub(r'(med.|thumb.)', 'original.',image["imgsrc"])
                try:
                    def progress(block_num, block_size, total_size):
                        pct = 100.00*((block_num * block_size)/total_size)
                        print("\r{:.0f}%".format(pct),file=sys.stderr,end='')
                    urllib.request.urlretrieve(imagesrc,"./img/roll20/{}/asset{}{}".format(book["id"],image["id"],imgext),progress)
                except urllib.error.HTTPError as e:
                    print(" |> Asset Error {}: {} {}".format(e.code,image["id"],imagesrc),file=sys.stderr,end='')
                    continue

            if image["width"] < 250 and image["height"] < 250 and image["width"]<(image["height"]*2):
                img = PIL.Image.open("./img/roll20/{}/asset{}{}".format(book["id"],image["id"],imgext))
                custom_config = r'--psm 8 --dpi 70 -l script/Latin'
                markerstr = pytesseract.image_to_string(img, config=custom_config).rstrip()
                if markerstr:
                    markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr)
                    if not markerref:
                        markerstr = pytesseract.image_to_string(img.crop((img.width*.1,img.height*.1,img.width*.8,img.height*.8)), config=custom_config).rstrip()
                        if markerstr.startswith('Yi'):
                            markerstr = 'Y1'+markerstr[2:]
                        markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr)
                    if markerref:
                        marker = ET.SubElement(mapentry,'marker')
                        ET.SubElement(marker,'name').text = markerref["name"]
                        ET.SubElement(marker,'color').text = '#ff0000'
                        ET.SubElement(marker,'shape').text = 'circle'
                        ET.SubElement(marker,'size').text = 'medium' if map['scale'] < 1.1 else 'large' if map['scale'] < 1.2 else 'huge'

                        ET.SubElement(marker,'hidden').text = 'YES'
                        ET.SubElement(marker,'locked').text = 'YES'
                        ET.SubElement(marker,'x').text = str(round(image["left"]*map["rescale"]))
                        ET.SubElement(marker,'y').text = str(round(image["top"]*map["rescale"]))
                        ET.SubElement(marker,'content',{ 'ref': markerref["ref"] })

            shutil.copy("./img/roll20/{}/asset{}{}".format(book["id"],image["id"],imgext),os.path.join(tempdir,"asset{}{}".format(image["id"],imgext)))
    if 'tiles' in map:
        for i in range(len(map["tiles"])):
            image = map["tiles"][i]
            print("\rtiles [{}/{}]".format(i,len(map["tiles"])),file=sys.stderr,end='')
            tile = ET.SubElement(mapentry,'tile')
            ET.SubElement(tile,'x').text = str(round((image["x"]-map["offsetX"]+(image["width"]*image["scale"]/2))*map["rescale"]))
            ET.SubElement(tile,'y').text = str(round((image["y"]-map["offsetY"]+(image["height"]*image["scale"]/2))*map["rescale"]))
            ET.SubElement(tile,'zIndex').text = str(image["z"])
            ET.SubElement(tile,'width').text = str(round(image["width"]*image["scale"]*map["rescale"]))
            ET.SubElement(tile,'height').text = str(round(image["height"]*image["scale"]*map["rescale"]))
            ET.SubElement(tile,'opacity').text = "1.0"
            ET.SubElement(tile,'rotation').text = str(image["rotation"])
            ET.SubElement(tile,'locked').text = "YES" if image["locked"] else "NO"
            ET.SubElement(tile,'layer').text = "object"
            ET.SubElement(tile,'hidden').text = "YES" if image["hidden"] else "NO"

            asset = ET.SubElement(tile,'asset')
            ET.SubElement(asset,'name').text = os.path.splitext(os.path.basename(image["img"]))[0]
            ET.SubElement(asset,'type').text = "image"
            imgext = os.path.splitext(os.path.basename(image["img"]))[1]
            img = PIL.Image.open("./data/"+image["img"])
            if imgext == ".webp":
                ET.SubElement(asset,'resource').text = mapslug+"_"+os.path.splitext(os.path.basename(image["img"]))[0]+".png"
                if img.width > 4096 or img.height > 4096:
                    scale = 4095/img.width if img.width>=img.height else 4095/img.height
                    img = img.resize((round(img.width*scale),round(img.height*scale)))
                img.save(os.path.join(tempdir,mapslug+"_"+os.path.splitext(os.path.basename(image["img"]))[0]+".png"))
            else:
                ET.SubElement(asset,'resource').text = mapslug+"_"+os.path.basename(image["img"])
                if img.width > 4096 or img.height > 4096:
                    scale = 4095/img.width if img.width>=img.height else 4095/img.height
                    img = img.resize((round(img.width*scale),round(img.height*scale)))
                    img.save(os.path.join(tempdir,mapslug+"_"+os.path.basename(image["img"])))
                else:
                    shutil.copy("./data/"+image["img"],os.path.join(tempdir,mapslug+"_"+os.path.basename(image["img"])))
            if img.width < 250 and img.height < 250:# and .9 <= image["width"]/image["height"] <= 1.1:
                #img = PIL.Image.open("./data/"+image["img"])
                markerref = None
                custom_config = r'--psm 8 --dpi 70 -l script/Latin'
                markerstr = pytesseract.image_to_string(trim(img), config=custom_config).rstrip()
                if markerstr:
                    markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)

                    if not markerref:
                        markerstr = pytesseract.image_to_string(img, config=custom_config).rstrip() or pytesseract.image_to_string(img.crop((img.width*.1,img.height*.1,img.width*.8,img.height*.8)), config=custom_config).rstrip()
                        if markerstr:
                            markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)
                if not markerref:
                    custom_config = r'--psm 10 --dpi 70 -l script/Latin'
                    markerstr = pytesseract.image_to_string(trim(img), config=custom_config).rstrip()
                    if markerstr:
                        markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)
                        if not markerref:
                            markerstr = pytesseract.image_to_string(img, config=custom_config).rstrip() or pytesseract.image_to_string(img.crop((img.width*.1,img.height*.1,img.width*.8,img.height*.8)), config=custom_config).rstrip()
                            if markerstr:
                                markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)
                if not markerref:
                    custom_config = r'--psm 10 --dpi 70 -l eng'
                    markerstr = pytesseract.image_to_string(trim(img), config=custom_config).rstrip()
                    if markerstr:
                        markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)
                        if not markerref:
                            markerstr = pytesseract.image_to_string(img, config=custom_config).rstrip() or pytesseract.image_to_string(img.crop((img.width*.1,img.height*.1,img.width*.8,img.height*.8)), config=custom_config).rstrip()
                            if markerstr:
                                markerref = markerSearch(mapname,markerstr) or markerSearch(altmapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None) or (markerSearch(mapname.split(":")[1].lstrip(),markerstr) if ":" in mapname else None) or (markerSearch(altmapname,floor+markerstr) if floor else None)
#                    if not markerref:
#                        markerstr = pytesseract.image_to_string(img.crop((img.width*.1,img.height*.1,img.width*.8,img.height*.8)), config=custom_config).rstrip()
#                        if markerstr == "Oo":
#                            markerstr = "O"
#                        if markerstr == "Cc":
#                            markerstr = "C"
#                        if markerstr.startswith('Yi'):
#                            markerstr = 'Y1'+markerstr[2:]
#                        markerref = markerSearch(mapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None)
#                        if not markerref:
#                            if markerstr.startswith('Yi'):
#                                markerstr = 'Y1'+markerstr[2:]
#                            markerstr = pytesseract.image_to_string(img.crop((img.width*.05,img.height*.05,img.width*.9,img.height*.9)), config=custom_config).rstrip()
#                            markerref = markerSearch(mapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None)
#                            if not markerref:
#                                markerstr = pytesseract.image_to_string(img.crop((img.width*.075,img.height*.075,img.width*.85,img.height*.85)), config=custom_config).rstrip()
#                                markerref = markerSearch(mapname,markerstr) or (markerSearch(mapname,floor+markerstr) if floor else None)
#                            
                if markerref:
                    if floor and floor != markerref["label"][0] and floor == markerref["name"][0]:
                        markerref["label"] = floor+markerref["label"]
                    marker = ET.SubElement(mapentry,'marker')
                    ET.SubElement(marker,'name').text = markerref["name"].split('.',2)[1].lstrip()
                    ET.SubElement(marker,'label').text = markerref["label"]
                    ET.SubElement(marker,'color').text = '#ff0000'
                    ET.SubElement(marker,'shape').text = 'circle'
                    ET.SubElement(marker,'size').text = 'medium' if map['scale'] < 1.1 else 'large' if map['scale'] < 1.2 else 'huge'

                    ET.SubElement(marker,'hidden').text = 'YES'
                    ET.SubElement(marker,'locked').text = 'YES'
                    ET.SubElement(marker,'x').text = str(round((image["x"]-map["offsetX"]+(image["width"]*image["scale"]/2))*map["rescale"]))
                    ET.SubElement(marker,'y').text = str(round((image["y"]-map["offsetY"]+(image["height"]*image["scale"]/2))*map["rescale"]))
                    ET.SubElement(marker,'content',{ 'ref': markerref["ref"] })
    return mapslug

bookfound = False
bookkey = "book"
if not args.adventure:
    with open("./data/books.json",encoding='utf-8') as f:
            b = json.load(f)
            f.close()
    for book in b[bookkey]:
        if args.book.lower() == book["id"].lower():
            bookfound = True
if args.adventure or not bookfound:
    args.adventure = True
    with open("./data/adventures.json",encoding='utf-8') as f:
            b = json.load(f)
            f.close()
    bookkey = "adventure"
for book in b[bookkey]:
    if not args.book:
        print("{:8s}: {}".format(book["id"],book["name"]))
        continue
    elif args.book.lower() != book["id"].lower():
        continue
    else:
        bookfound = True
    print("{}".format(book["name"]))
    filemask = "./data/book/book-{}.json" if not args.adventure else "./data/adventure/adventure-{}.json"
    with open(filemask.format(book["id"].lower())) as f:
        data = json.load(f)
        f.close()
    plid = book["id"].lower()
    if plid == 'idrotf':
        plid = 'idrotfm'
    if not os.path.exists("./data/worlds/{}".format(plid)):
        try:
            def progress(block_num, block_size, total_size):
                pct = 100.00*((block_num * block_size)/total_size)
                print("\rDownloading Plutonium maps {:.2f}%".format(pct),file=sys.stderr,end='')

            urllib.request.urlretrieve("https://foundry.5e.tools/plutonium/{0}/{0}.zip".format(plid), "./data/worlds/{}.zip".format(plid),progress)
            with zipfile.ZipFile("./data/worlds/{}.zip".format(plid),'r') as zip:
                    zip.extractall("./data/worlds/")
                    zip.close()

            os.remove("./data/worlds/{}.zip".format(plid))
        except urllib.error.HTTPError as e:
            print(" |> Download Error: {}".format(e.code),file=sys.stderr)
    if os.path.exists("./data/worlds/{}/data/scenes.db".format(plid)):
        with open("./data/worlds/{}/data/scenes.db".format(plid),encoding='utf-8') as f:
            l = f.readline()
            book['maps'] = []
            while l:
                map = json.loads(l)
                if len(map["img"]) > 0 or len(map["tiles"]) > 0:
                    book["maps"].append(map)
                l = f.readline()
            f.close()
    if os.path.exists("./data/roll20-module/roll20-module-{}.json".format(book["id"].lower())):
        with open("./data/roll20-module/roll20-module-{}.json".format(book["id"].lower()),encoding='utf-8') as f:
            r20 = json.load(f)
            if "maps" in book:
                for map in r20["maps"]:
                    mapexists = False
                    for fmap in book["maps"]:
                        if map["attributes"]["name"] == fmap["name"]:
                            mapexists = True
                            break
                    if not mapexists:
                        map["name"] = map["attributes"]["name"]
                        book["maps"].append(map)
            else:
                book["maps"] = r20["maps"]
            f.close()
    if 'author' not in book:
        book['author'] = "Wizards RPG Team"
    global bookuuid
    global bookref

    bookref = book
    bookuuid = uuid.uuid5(nsuuid,book["id"])
    slugs = []
    module = ET.Element(
        'module', { 'id': str(bookuuid),'version': "{:.0f}".format(time.time()) } )
    name = ET.SubElement(module, 'name')
    name.text = book['name']
    author = ET.SubElement(module, 'author')
    author.text = book['author']
    category = ET.SubElement(module, 'category')
    category.text = "rules"
    code = ET.SubElement(module, 'code')
    code.text = book['id']
    image = ET.SubElement(module, 'image')
    if os.path.exists("img/dndbeyond/{}.jpeg".format(book['name'])):
        with Image(filename="img/dndbeyond/{}.jpeg".format(book['name'])) as img:
            img.crop(width=img.width, height=int(img.width/1.5), gravity='north')
            img.save(filename=os.path.join(tempdir,"{}_cover.png".format(book['id'])))
        image.text = "{}_cover.png".format(book['id'])
    elif os.path.exists("img/dndbeyond/{}.jpeg".format(book['id'])):
        with Image(filename="img/dndbeyond/{}.jpeg".format(book['id'])) as img:
            img.crop(width=img.width, height=int(img.width/1.5), gravity='north')
            img.save(filename=os.path.join(tempdir,"{}_cover.png".format(book['id'])))
        image.text = "{}_cover.png".format(book['id'])
    elif os.path.exists("img/dndbeyond/{}.jpeg".format(book['name'].split(': ')[-1])):
        with Image(filename="img/dndbeyond/{}.jpeg".format(book['name'].split(': ')[-1])) as img:
            img.crop(width=img.width, height=int(img.width/1.5), gravity='north')
            img.save(filename=os.path.join(tempdir,"{}_cover.png".format(book['id'])))
        image.text = "{}_cover.png".format(book['id'])
    elif os.path.exists("img/dndbeyond/{}.jpeg".format(book['name'].split(': ')[0])):
        with Image(filename="img/dndbeyond/{}.jpeg".format(book['name'].split(': ')[0])) as img:
            img.crop(width=img.width, height=int(img.width/1.5), gravity='north')
            img.save(filename=os.path.join(tempdir,"{}_cover.png".format(book['id'])))
        image.text = "{}_cover.png".format(book['id'])
    else:
        image.text = os.path.basename(book['coverUrl'])
        shutil.copy(book['coverUrl'],os.path.join(tempdir,os.path.basename(book['coverUrl'])))
    slug = ET.SubElement(module, 'slug')
    slug.text = slugify(book['name'])
    description = ET.SubElement(module, 'description')
    description.text = ""
    if args.adventure:
        if 'custom' in book['level']:
            description.text += "An adventure for {}\nStoryline: {}\n".format(book['level']['custom'],book['storyline'])
        else:
            description.text += "An adventure for levels {} to {}\nStoryline: {}\n".format(book['level']['start'],book['level']['end'],book['storyline'])
    description.text += "By {}\nPublished {}".format(book['author'],book['published'])
    
    needmanualbreak = True
    for section in book['contents']:
        if 'headers' in section:
            for header in section['headers']:
                if type(header) == dict and re.match(r'^([A-Za-z]*?[0-9,-]+[A-Za-z]?|[A-Z])\. ',header['header']):
                    needmanualbreak = False
                    break
        if not needmanualbreak:
            break
    if needmanualbreak:
        args.manualbreak = True
        print("This needs a manual breakout",file=sys.stderr)

                    

    order = 0
    for d in data['data']:
        if d['type'] == "section":
            order += 1
            processSection(order,d,module)
            print("\rConverting sections [{}/{}] {:.0f}%".format(order,len(data['data']),order/len(data['data'])*100),file=sys.stderr,end='')
        else:
            print("Need to handle type: ",data['type'])
    mapcount = 0
    if 'maps' in book:
        mapsbaseslug = 'maps'
        mapsslug = mapsbaseslug + str(len([i for i in slugs if mapsbaseslug in i]))
        mapgroup = str(uuid.uuid5(bookuuid,mapsslug))
        group = ET.SubElement(module, 'group', {'id': mapgroup, 'sort': str(order+1)})
        ET.SubElement(group, 'name').text = "Maps"
        ET.SubElement(group, 'slug').text = mapsslug
        for map in book['maps']:
            mapcount += 1
            sys.stderr.write("\033[K")
            print("\rConverting maps [{}/{}] {:.0f}%".format(mapcount,len(book['maps']),mapcount/len(book['maps'])*100),file=sys.stderr,end='')
            createMap(map,mapgroup)


if args.book and bookfound:
    # write to file
    sys.stderr.write("\033[K")
    print("\rWriting XML",file=sys.stderr,end='')
    tree = ET.ElementTree(utils.indent(module, 1))
    tree.write(os.path.join(tempdir,"module.xml"), xml_declaration=True, short_empty_elements=False, encoding='utf-8')
    zipfilename = "book-{}.module".format(args.book)
   # zipfile = shutil.make_archive("module","zip",tempdir)
    if args.output:
        zipfilename = args.output
    with zipfile.ZipFile(zipfilename, 'w',compression=zipfile.ZIP_DEFLATED) as zipObj:
       # Iterate over all the files in directory
       for folderName, subfolders, filenames in os.walk(tempdir):
           for filename in filenames:
               #create complete filepath of file in directory
               filePath = os.path.join(folderName, filename)
               # Add file to zip
               sys.stderr.write("\033[K")
               print("\rAdding: {}".format(filename),file=sys.stderr,end='')
               zipObj.write(filePath, os.path.basename(filePath)) 
    sys.stderr.write("\033[K")
    print("\rDeleteing temporary files",file=sys.stderr,end='')
    shutil.rmtree(tempdir)
    sys.stderr.write("\033[K")
    print("\rFinished creating module: {}".format(zipfilename),file=sys.stderr)

#os.rename(zipfile,args.output)
#    else:
#        os.rename(zipfile,"book-{}.module".format(args.book))
