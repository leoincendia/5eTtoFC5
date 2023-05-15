# vim: set tabstop=8 softtabstop=0 expandtab shiftwidth=4 smarttab : #
import xml.etree.cElementTree as ET
import re
import utils
import json
import os
import copy
import requests
from slugify import slugify
from shutil import copyfile

def parseMonster(m, compendium, args, fluff, lGroup):
    if '_copy' in m:
        if args.verbose:
            print("COPY: " + m['name'] + " from " + m['_copy']['name'] + " in " + m['_copy']['source'])
        xtrsrc = "./data/bestiary/bestiary-" + m['_copy']['source'].lower() + ".json"
        try:
            with open(xtrsrc,encoding="utf-8") as f:
                d = json.load(f)
                f.close()
            mcpy = copy.deepcopy(m)
            for mn in d['monster']:
                if mn['name'].lower() == mcpy['_copy']['name'].lower():
                    if '_copy' in mn:
                        if args.verbose:
                            print("ANOTHER COPY: " + mn['name'] + " from " + mn['_copy']['name'] + " in " + mn['_copy']['source'])
                        xtrsrc2 = "./data/bestiary/bestiary-" + mn['_copy']['source'].lower() + ".json"
                        with open(xtrsrc2,encoding="utf-8") as f:
                            d2 = json.load(f)
                            f.close()
                        for mn2 in d2['monster']:
                            if mn2['name'] == mn['_copy']['name']:
                                mn = copy.deepcopy(mn2)
                                break
                    m = copy.deepcopy(mn)
                    m['name'] = mcpy['name']
                    if 'isNpc' in mcpy:
                        m['isNpc'] = mcpy['isNpc']
                    m['source'] = mcpy['source']
                    if "otherSources" in mcpy:
                        m["otherSources"] = mcpy["otherSources"]
                    elif "otherSources" in m:
                        del m["otherSources"]
                    if 'size' in mcpy:
                        m['size'] = mcpy['size']
                    if 'hp' in mcpy:
                        m['hp'] = mcpy['hp']
                    if 'original_name' in mcpy:
                        m['original_name'] = mcpy['original_name']
                    if 'page' in mcpy:
                        m['page'] = mcpy['page']
                    elif 'page' in m:
                        del m['page']
                    if 'image' in mcpy:
                        m['image'] = mcpy['image']
                    if '_mod' in mcpy['_copy']:
                        m = utils.modifyMonster(m,mcpy['_copy']['_mod'])
                    break
            if '_trait' in mcpy['_copy']:
                if args.verbose:
                    print("Adding extra traits for: " + mcpy['_copy']['_trait']['name'])
                traits = "./data/bestiary/traits.json"
                with open(traits,encoding="utf-8") as f:
                    d = json.load(f)
                    f.close()
                for trait in d['trait']:
                    if trait['name'] == mcpy['_copy']['_trait']['name']:
                        if '_mod' in trait['apply']:
                            m = utils.modifyMonster(m,trait['apply']['_mod'])
                        if '_root' in trait['apply']:
                            for key in trait['apply']['_root']:
                                if key == "speed" and type(trait['apply']['_root'][key]) == int:
                                    for k2 in m['speed']:
                                            m['speed'][k2]=trait['apply']['_root'][key]
                                else:
                                    m[key] = trait['apply']['_root'][key]
        except IOError as e:
            if args.verbose:
                print ("Could not load additional source ({}): {}".format(e.errno, e.strerror))
            return
#    for eachmonsters in compendium.findall('monster'):
#        if eachmonsters.find('name').text == m['name']:
#            m['name'] = "{} (DUPLICATE IN {})".format(m['name'],m['source'])
    monster = ET.SubElement(compendium, 'monster')
    name = ET.SubElement(monster, 'name')
    name.text = utils.fixTags(m['name'],m,args.nohtml)

    #print(ET.tostring(name).decode())

    size = ET.SubElement(monster, 'size')
    size.text = m['size'][0]

    typ = ET.SubElement(monster, 'type')
    if isinstance(m['type'], dict):
        if 'swarmSize' in m['type']:
            typ.text = "Swarm of {} {}s".format(
                utils.convertSize(m['type']['swarmSize']), str.capitalize(m['type']['type']))
        elif 'tags' in m['type']:
            subtypes = []
            for tag in m['type']['tags']:
                if not isinstance(tag, dict):
                    subtypes.append(tag)
                else:
                    subtypes.append(tag['prefix'] + tag['tag'])
            typ.text = "{} ({})".format(str.capitalize(m['type']['type']), str.capitalize(", ".join(subtypes)))
        else:
            typ.text = str.capitalize(m['type']['type'])
    else:
        typ.text = str.capitalize(m['type'])

    if 'alignment' in m:
        alignment = ET.SubElement(monster, 'alignment')
        alignment.text = utils.convertAlignList(m['alignment'])

    ac = ET.SubElement(monster, 'ac')
    acstr = []
    for acs in m['ac']:
        if isinstance(acs, dict):
            if len(acstr) == 0:
                if 'ac' in acs:
                    acstr.append(str(acs['ac']))
                if 'from' in acs and 'condition' in acs:
                    acstr.append(utils.fixTags(", ".join(acs['from']) + " " + acs['condition'],m,True))
                elif 'from' in acs:
                    acstr.append(utils.fixTags(", ".join(acs['from']),m,True))
                elif 'condition' in acs:
                    acstr.append(utils.fixTags(acs['condition'],m,True))
                if 'special' in acs:
                    acstr.append(utils.fixTags(acs['special'],m,True))
                continue
            acstr.append(utils.fixTags("{}".format(
                "{} {}".format(
                    acs['ac'],
                    "("+", ".join(acs['from']) + ") " + acs['condition'] if 'from' in acs and 'condition' in acs else
                    "("+", ".join(acs['from'])+")" if 'from' in acs else
                    acs['condition']
                    ) if 'from' in acs or 'condition' in acs else acs['ac']),m,True))
        else:
            acstr.append(str(acs))
    if len(acstr) > 1:
        ac.text = "{} ({})".format(acstr[0],", ".join(acstr[1:])) 
    elif acstr[0]:
        ac.text = acstr[0]
    else:
        ac.text = "0"

    hp = ET.SubElement(monster, 'hp')
    if "special" in m['hp']:
        if args.nohtml and re.match(r'equal the .*?\'s Constitution modifier',m['hp']['special']):
            hp.text = str(utils.getAbilityMod(m['con']))
            if 'trait' in m:
                m['trait'].insert(0,{"name": "Hit Points","entries": [ m['hp']['special'] ]})
            else:
                m['trait'] = [ {"name": "Hit Points","entries": [ m['hp']['special'] ]} ]
        elif args.nohtml:
            hpmatch = re.match(r'[0-9]+ ?(\([0-9]+[Dd][0-9]+( ?\+ ?[0-9]+)?\))?', m['hp']['special'])
            if hpmatch:
                hp.text = str(hpmatch.group(0)).rstrip()
            else:
                hp.text = "0"
            if 'trait' in m:
                m['trait'].insert(0,{"name": "Hit Points","entries": [ m['hp']['special'] ]})
            else:
                m['trait'] = [ {"name": "Hit Points","entries": [ m['hp']['special'] ]} ]
        else:
            hp.text = m['hp']['special']
    else:
        if 'formula' not in m['hp']:
            hp.text = str(m['hp']['average'])
        else:
            hp.text = "{} ({})".format(m['hp']['average'], m['hp']['formula'])

    speed = ET.SubElement(monster, 'speed')
    if type(m['speed']) == str:
        speed.text = m['speed']
    elif 'choose' in m['speed']:
        lis = []
        for key, value in m['speed'].items():
            if key == "walk":
                lis.append(str(value) + " ft.")
            elif key == "choose":
                value['from'].insert(-1, 'or')
                lis.append(
                    "{} {} ft. {}".format(
                        " ".join(
                            value['from']),
                        value['amount'],value['note']))
            else:
                lis.append("{} {} ft.".format(key, value))
        lis.sort()
        speed.text = ", ".join(lis)
    else:
        def getSpeed(speedobj):
            speeds = []
            for key,value in speedobj.items():
                if isinstance(value,bool):
                    continue
                if isinstance(value,list) and len(value) == 1:
                    value = value[0]
                if key == "alternate":
                    speed = "or "+getSpeed(value)
                elif isinstance(value,dict):
                    speed = "{} {} ft. {}".format(
                            key,
                            value['number'],
                            value['condition']
                            )
                else:
                    speed = "{} {} ft.".format(
                            key, value)
                speeds.append(speed.replace("walk ",""))
            speeds.sort()
            return ", ".join(speeds)

        speed.text = getSpeed(m['speed'])

    statstr = ET.SubElement(monster, 'str')
    statstr.text = str(m['str'] if 'str' in m else '0')
    statdex = ET.SubElement(monster, 'dex')
    statdex.text = str(m['dex'] if 'dex' in m else '0')
    statcon = ET.SubElement(monster, 'con')
    statcon.text = str(m['con'] if 'con' in m else '0')
    statint = ET.SubElement(monster, 'int')
    statint.text = str(m['int'] if 'int' in m else '0')
    statwis = ET.SubElement(monster, 'wis')
    statwis.text = str(m['wis'] if 'wis' in m else '0')
    statcha = ET.SubElement(monster, 'cha')
    statcha.text = str(m['cha'] if 'cha' in m else '0')
    if 'isNpc' in m and m['isNpc'] and not args.nohtml:
        npcroll = ET.SubElement(monster, 'role')
        npcroll.text = "ally"

    if 'save' in m:
        save = ET.SubElement(monster, 'save')
        save.text = ", ".join(["{} {}".format(str.capitalize(
            key), value) for key, value in m['save'].items()])

    if 'skill' in m:
        skill = ET.SubElement(monster, 'skill')
        skills = []
        for key, value in m['skill'].items():
            if type(value) == str:
                skills.append("{} {}".format(str.capitalize(key), value))
            else:
                if key == "other":
                    for sk in value:
                        if "oneOf" in sk:
                            if args.nohtml:
                                if 'trait' not in m: m['trait'] = []
                                m['trait'].insert(0,{"name": "Skills","entries": [ "plus one of the following: "+", ".join(["{} {}".format(str.capitalize(ook), oov) for ook, oov in sk["oneOf"].items()]) ] })
                            else:
                                skills.append("plus one of the following: "+", ".join(["{} {}".format(str.capitalize(ook), oov) for ook, oov in sk["oneOf"].items()]))
        skills.sort()
        skill.text = ", ".join(skills)

    if 'vulnerable' in m:
        vulnerable = ET.SubElement(monster, 'vulnerable')
        vulnerablelist = utils.parseRIV(m, 'vulnerable')
        vulnerable.text = ", ".join(vulnerablelist)

    if 'resist' in m:
        resist = ET.SubElement(monster, 'resist')
        resistlist = utils.parseRIV(m, 'resist')
        resist.text = ", ".join(resistlist)

    if 'immune' in m:
        immune = ET.SubElement(monster, 'immune')
        immunelist = utils.parseRIV(m, 'immune')
        immune.text = ", ".join(immunelist)

    if 'conditionImmune' in m:
        conditionImmune = ET.SubElement(monster, 'conditionImmune')
        conditionImmunelist = utils.parseRIV(m, 'conditionImmune')
        conditionImmune.text = ", ".join(conditionImmunelist)

    if 'senses' in m:
        senses = ET.SubElement(monster, 'senses')
        senses.text = ", ".join([x for x in m['senses']])
        
    if 'passive' in m:
        passive = ET.SubElement(monster, 'passive')
        passive.text = str(m['passive'])

    languages = ET.SubElement(monster, 'languages')
    if 'languages' in m:
        languageList = utils.parseRIV(m, 'languages')
        languages.text = ", ".join(languageList)
    else:
        languages.text = "—"

    if 'cr' in m:
        cr = ET.SubElement(monster, 'cr')
        if isinstance(m['cr'], dict):
            cr.text = str(m['cr']['cr'])
        else:
            if not m['cr'] == "Unknown":
                cr.text = str(m['cr'])

    if 'source' in m and not args.srd:
        slug = slugify(m["name"])
        if args.addimgs and os.path.isdir("img") and not os.path.isfile(os.path.join(args.tempdir,"monsters", slug + ".png")) and not os.path.isfile(os.path.join(args.tempdir,"monsters",slug+".jpg")) and not os.path.isfile(os.path.join(args.tempdir,"monsters", "token_" + slug + ".png")) and not os.path.isfile(os.path.join(args.tempdir,"monsters", "token_" + slug + ".jpg")):
            if not os.path.isdir(os.path.join(args.tempdir,"monsters")):
                os.mkdir(os.path.join(args.tempdir,"monsters"))
            #if not os.path.isdir(os.path.join(args.tempdir,"tokens")):
            #    os.mkdir(os.path.join(args.tempdir,"tokens"))
            if 'image' in m:
                artworkpath = m['image']
                if m['image'] and not os.path.isfile("img/"+m['image']):
                    if args.verbose:
                        print("Downloading",m['image'])
                    req = requests.get("https://5e.tools/"+artworkpath)
                    if not os.path.exists(os.path.join("img",os.path.dirname(artworkpath))):
                        os.makedirs(os.path.join("img",os.path.dirname(artworkpath)),exist_ok=True)
                    with open(os.path.join("img",artworkpath), 'wb') as f:
                        f.write(req.content)
                        f.close()
            else:
                artworkpath = None
            monstername = m["original_name"] if "original_name" in m else m["name"]
            if artworkpath and os.path.isfile("./img/" + artworkpath):
                artworkpath = "./img/" + artworkpath
            elif os.path.isfile("./img/bestiary/" + m["source"] + "/" + monstername + ".jpg"):
                artworkpath = "./img/bestiary/" + m["source"] + "/" + monstername + ".jpg"
            elif os.path.isfile("./img/bestiary/" + m["source"] + "/" + monstername + ".png"):
                artworkpath = "./img/bestiary/" + m["source"] + "/" + monstername + ".png"
            elif os.path.isfile("./img/vehicles/" + m["source"] + "/" + monstername + ".jpg"):
                artworkpath = "./img/vehicles/" + m["source"] + "/" + monstername + ".jpg"
            elif os.path.isfile("./img/vehicles/" + m["source"] + "/" + monstername + ".png"):
                artworkpath = "./img/vehicles/" + m["source"] + "/" + monstername + ".png"
            if artworkpath is not None:
                ext = os.path.splitext(artworkpath)[1]
                copyfile(artworkpath, os.path.join(args.tempdir,"monsters",slug + ext))
                imagetag = ET.SubElement(monster, 'image')
                imagetag.text = slug + ext
            if os.path.isfile("./img/" + m["source"] + "/" + monstername + ".png") or os.path.isfile("./img/" + m["source"] + "/" + monstername + ".jpg"):
                if os.path.isfile("./img/" + m["source"] + "/" + monstername + ".png"):
                    artworkpath = "./img/" + m["source"] + "/" + monstername + ".png"
                else:
                    artworkpath = "./img/" + m["source"] + "/" + monstername + ".jpg"
                ext = os.path.splitext(artworkpath)[1]
                copyfile(artworkpath, os.path.join(args.tempdir,"monsters","token_" + slug + ext))
                imagetag = ET.SubElement(monster, 'token')
                imagetag.text = slug + ext
            elif os.path.isfile("./img/vehicles/tokens/" + m["source"] + "/" + monstername + ".png") or os.path.isfile("./img/vehicles/tokens/" + m["source"] + "/" + monstername + ".jpg"):
                if os.path.isfile("./img/vehicles/tokens/" + m["source"] + "/" + monstername + ".png"):
                    artworkpath = "./img/vehicles/tokens/" + m["source"] + "/" + monstername + ".png"
                else:
                    artworkpath = "./img/vehicles/tokens/" + m["source"] + "/" + monstername + ".jpg"
                ext = os.path.splitext(artworkpath)[1]
                copyfile(artworkpath, os.path.join(args.tempdir,"monsters","token_" + slug + ext))
                imagetag = ET.SubElement(monster, 'token')
                imagetag.text = "token_" + slug + ext
        elif args.addimgs and os.path.isfile(os.path.join(args.tempdir,"monsters", slug + ".png")):
            imagetag = ET.SubElement(monster, 'image')
            imagetag.text = slug + ".png"
        elif args.addimgs and os.path.isfile(os.path.join(args.tempdir,"monsters", slug + ".jpg")):
            imagetag = ET.SubElement(monster, 'image')
            imagetag.text = slug + ".jpg"
        elif args.addimgs and os.path.isfile(os.path.join(args.tempdir,"monsters", "token_" + slug + ".png")):
            imagetag = ET.SubElement(monster, 'token')
            imagetag.text = "token_" + slug + ".png"
        elif args.addimgs and os.path.isfile(os.path.join(args.tempdir,"monsters", "token_" + slug + ".jpg")):
            imagetag = ET.SubElement(monster, 'token')
            imagetag.text = "token_" + slug + ".jpg"

        sourcetext = "{}, page {}".format(
            utils.getFriendlySource(m['source'],args), m['page']) if 'page' in m and m['page'] != 0 else utils.getFriendlySource(m['source'],args)

        if 'otherSources' in m and m["otherSources"] is not None:
            for s in m["otherSources"]:
                if "source" not in s:
                    continue
                sourcetext += "; "
                sourcetext += "{}, page {}".format(
                    utils.getFriendlySource(s["source"],args), s["page"]) if 'page' in s and s["page"] != 0 else utils.getFriendlySource(s["source"],args)
        #trait = ET.SubElement(monster, 'trait')
        #name = ET.SubElement(trait, 'name')
        #name.text = "Source"
        #text = ET.SubElement(trait, 'text')
        #text.text = sourcetext
        #if not args.nohtml:
        #    srctag = ET.SubElement(monster, 'source')
        #    srctag.text = sourcetext
    else:
        sourcetext = None


    if 'trait' in m:
        for t in m['trait']:
            trait = ET.SubElement(monster, 'trait')
            name = ET.SubElement(trait, 'name')
            name.text = utils.remove5eShit(t['name']) + "."
            if "entries" not in t:
                t["entries"] = []
            text = ET.SubElement(trait, 'text')
            text.text = utils.getEntryString(t["entries"],m,args)
            #for e in utils.getEntryString(t["entries"],m,args).split("\n"):
            #    text = ET.SubElement(trait, 'text')
            #    text.text = e
                      
    if 'action' in m and m['action'] is not None:
        for t in m['action']:
            action = ET.SubElement(monster, 'action')
            if 'name' in t:
                name = ET.SubElement(action, 'name')
                name.text = utils.remove5eShit(t['name']) +"."
            text = ET.SubElement(action, 'text')
            text.text = utils.getEntryString(t["entries"],m,args)
            #for e in utils.getEntryString(t["entries"],m,args).split("\n"):
            #    text = ET.SubElement(action, 'text')
            #    text.text = e
                #for match in re.finditer(r'(((\+|\-)?[0-9]*) to hit.*?|DC [0-9]+ .*? saving throw.*?)\(([0-9Dd\+\- ]+)\) .*? damage',e):
                #    if match.group(4):
                #        attack = ET.SubElement(action, 'attack')
                #        attack.text = "{}|{}|{}".format(utils.remove5eShit(t['name']) if 'name' in t else "",match.group(2).replace(' ','') if match.group(2) else "",match.group(4).replace(' ',''))
     
    if 'spellcasting' in m:
        spells = []
        slots = []
        for s in m['spellcasting']:
            trait = ET.SubElement(monster, 'action')
            name = ET.SubElement(trait, 'name')
            name.text = utils.remove5eShit(s['name']) + "."
            for e in s['headerEntries']:
                text = ET.SubElement(trait, 'text')
                text.text = utils.fixTags(e,m,args.nohtml)
            trait = ET.SubElement(monster, 'action')
            if "will" in s:
                text = ET.SubElement(trait, 'text')
                willspells = s['will']
                text.text = "At will: " + \
                    ", ".join([utils.fixTags(e['entry'] if type(e) == dict else e,m,args.nohtml) for e in willspells if type(e) == str or (type(e) == dict and not e['hidden'])])
                for spl in willspells:
                    if type(spl) == dict:
                        spl = spl['entry']
                    search = re.search(
                        r'{@spell+ (.*?)(\|.*)?}', spl, re.IGNORECASE)
                    if search is not None:
                        spells.append(search.group(1))

            if "daily" in s:
                for timeframe, lis in s['daily'].items():
                    text = ET.SubElement(trait, 'text')
                    dailyspells = lis
                    t = "{}/day{}: ".format(timeframe[0],
                                            " each" if len(timeframe) > 1 else "")
                    text.text = t + \
                        ", ".join([utils.fixTags(e['entry'] if type(e) == dict else e,m,args.nohtml) for e in dailyspells if type(e) == str or (type(e) == dict and not e['hidden'])])
                    for spl in dailyspells:
                        if type(spl) == dict:
                            spl = spl['entry']
                        search = re.search(
                            r'{@spell+ (.*?)(\|.*)?}', spl, re.IGNORECASE)
                        if search is not None:
                            spells.append(search.group(1))

            if "spells" in s:
                slots = []
                for level, obj in s['spells'].items():
                    text = ET.SubElement(trait, 'text')
                    spellbois = obj['spells']
                    t = "{} level ({} slots): ".format(
                        utils.ordinal(
                            int(level)),
                        obj['slots'] if 'slots' in obj else 0) if level != "0" else "Cantrips (at will): "
                    if level != "0":
                        slots.append(
                            str(obj['slots'] if 'slots' in obj else 0))
                    text.text = t + \
                        ", ".join([utils.fixTags(e,m,args.nohtml) for e in spellbois])
                    for spl in spellbois:
                        search = re.search(
                            r'{@spell+ (.*?)(\|.*)?}', spl, re.IGNORECASE)
                        if search is not None:
                            spells.append(search.group(1))
            if 'footerEntries' in s:
                for e in s['footerEntries']:
                    text = ET.SubElement(trait, 'text')
                    text.text = utils.fixTags(e,m,args.nohtml)

    if 'bonus' in m and m['bonus'] is not None:
        for t in m['bonus']:
            action = ET.SubElement(monster, 'bonus')
            if 'name' in t:
                name = ET.SubElement(action, 'name')
                name.text = utils.remove5eShit(t['name']) + "."
            
            text = ET.SubElement(action, 'text')
            text.text = utils.getEntryString(t["entries"],m,args)

            #for e in utils.getEntryString(t["entries"],m,args).split("\n"):
            #    text = ET.SubElement(action, 'text')
            #    text.text = utils.remove5eShit(e)
                #for match in re.finditer(r'(((\+|\-)?[0-9]*) to hit.*?|DC [0-9]+ .*? saving throw.*?)\(([0-9Dd\+\- ]+)\) .*? damage',e):
                #    if match.group(4):
                #        attack = ET.SubElement(action, 'attack')
                #        attack.text = "{}|{}|{}".format(utils.remove5eShit(t['name']) if 'name' in t else "",match.group(2).replace(' ','') if match.group(2) else "",match.group(4).replace(' ',''))

    if 'reaction' in m and m['reaction'] is not None:
        for t in m['reaction']:
            action = ET.SubElement(monster, 'reaction')
            name = ET.SubElement(action, 'name')
            name.text = utils.remove5eShit(t['name']) + "."
            text = ET.SubElement(action, 'text')
            text.text = utils.getEntryString(t["entries"],m,args)
            #for e in utils.getEntryString(t["entries"],m,args).split("\n"):
            #    text = ET.SubElement(action, 'text')
            #    text.text = e

    if 'variant' in m and m['variant'] is not None:
        if type(m['variant']) != list:
            m['variant'] = [ m['variant'] ]
        for t in m['variant']:
            action = ET.SubElement(monster, 'action')
            name = ET.SubElement(action, 'name')
            name.text = "Variant: " + utils.remove5eShit(t['name']) + "."
            for e in utils.getEntryString(t["entries"],m,args).split("\n"):
                text = ET.SubElement(action, 'text')
                text.text = e

    if 'legendary' in m:
        legendary = ET.SubElement(monster, 'legendary')

        if "legendaryHeader" in m:
            for h in m['legendaryHeader']:
                text = ET.SubElement(legendary, 'text')
                text.text = utils.remove5eShit(h)
        else:
            text = ET.SubElement(legendary, 'text')
            if "isNamedCreature" in m and m['isNamedCreature']:
                text.text = "{0} can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature’s turn. {0} regains spent legendary actions at the start of its turn.".format(utils.fixTags(m['name'],m,args.nohtml).split(',', 1)[0])
            else:
                text.text = "The {0} can take 3 legendary actions, choosing from the options below. Only one legendary action can be used at a time and only at the end of another creature’s turn. The {0} regains spent legendary actions at the start of its turn.".format(str.lower(m['name']))
        legendary = ET.SubElement(monster, 'legendary')
        for t in m['legendary']:
            text = ET.SubElement(legendary, 'text')
            if 'name' not in t:
                t['name'] = ""
            text.text = "<b>" + utils.remove5eShit(t['name']) + ".</b> " + utils.getEntryString(t["entries"],m,args)

    if 'mythic' in m:
        if "mythicHeader" in m:
            for h in m['mythicHeader']:
                mythic = ET.SubElement(monster, 'mythic')
                text = ET.SubElement(mythic, 'text')
                text.text = utils.remove5eShit(h)
        for t in m['mythic']:
            mythic = ET.SubElement(monster, 'mythic')
            name = ET.SubElement(mythic, 'name')
            if 'name' not in t:
                t['name'] = ""
            name.text = utils.remove5eShit(t['name'])
            for e in utils.getEntryString(t["entries"],m,args).split("\n"):
                text = ET.SubElement(mythic, "text")
                text.text = e

    description = ET.SubElement(monster, 'description')
    description.text = ''
    if 'fluff' in m and not args.srd:
        for e1 in fluff:
            if e1['name'] != m['name']:
                continue

            if 'entries' in e1:
                description.text += getDesc(e1['entries'],m)

    if 'legendaryGroup' in m:
        named = ""
        if "isNamedCreature" in m and m['isNamedCreature']:
            named = "-s"
        description.text += "\n<i><a href=\"/monster/" + slugify(m['name'].split(',', 1)[0]) + named + "-lair\">Has Lair Actions</a></i>"
    if sourcetext: description.text += "\n<b>Source:</b> {}".format(sourcetext)
    if args.nohtml:
        description.text = re.sub('</?(i|b|spell)>', '', description.text)
    if 'environment' in m:
        environment = ET.SubElement(monster, 'environment')
        environment.text = ", ".join([x for x in m['environment']])
    image = ET.SubElement(monster, 'image')
    image.text = m['name'] + '_tob3.webp'
    token = ET.SubElement(monster, 'token')
    token.text = m['name'] + '_token_tob3.webp'

    if 'legendaryGroup' in m:
        #with open("./data/legendarygroups.json",encoding="utf-8") as f:
        #    meta = json.load(f)
        #    f.close()
        for l in lGroup: #meta['legendaryGroup']:
            if l['name'] != m['legendaryGroup']['name']:
                continue
            lair = ET.SubElement(compendium, 'monster')
            lname = ET.SubElement(lair, 'name')
            named = ""
            if "isNamedCreature" in m and m['isNamedCreature']:
               named = "’s"
            lname.text = utils.fixTags(m['name'],m,args.nohtml).split(',', 1)[0] + named + " Lair"
            lsize = ET.SubElement(lair, 'size')
            lsize.text = "L"
            ltype = ET.SubElement(lair, 'type')
            ltype.text = "Lair"
            if 'lairActions' in l:
                legendary = ET.SubElement(lair, 'trait')
                name = ET.SubElement(legendary, 'text')
                name.text = "Lair Actions"
                if not args.nohtml:
                    name.text = "<u><b>{}</b></u>".format(name.text)
                for t in l['lairActions']:
                    if type(t) == str:
                        text = ET.SubElement(legendary, 'text')
                        text.text = utils.fixTags(t,m,args.nohtml)
                        continue
                    if 'name' in t:
                        name = ET.SubElement(legendary, 'text')
                        name.text = "Lair Action: " + utils.remove5eShit(t['name'])
                    if t['type'] == 'list':
                        for i in t['items']:
                            text = ET.SubElement(legendary, 'text')
                            text.text = "<b>•</b> <i><b>" + i["name"] + "</b></i> " + utils.fixTags(i["entry"],m,args.nohtml)
                        continue
                    for e in utils.getEntryString(t["entries"],m,args).split("\n"):
                        text = ET.SubElement(legendary, 'text')
                        text.text = e

            if 'regionalEffects' in l:
                legendary = ET.SubElement(lair, 'trait')
                name = ET.SubElement(legendary, 'text')
                name.text = "Regional Effects"
                if not args.nohtml:
                    name.text = "<u><b>{}</b></u>".format(name.text)
                for t in l['regionalEffects']:
                    if type(t) == str:
                        text = ET.SubElement(legendary, 'text')
                        text.text = utils.fixTags(t,m,args.nohtml)
                        continue
                    if 'name' in t:
                        name = ET.SubElement(legendary, 'text')
                        name.text = "Regional Effect: " + utils.remove5eShit(t['name'])
                    if t['type'] == 'list':
                        for i in t['items']:
                            text = ET.SubElement(legendary, 'text')
                            text.text = "<b>•</b> <i><b>" + i["name"] + "</b></i> " + utils.fixTags(i["entry"],m,args.nohtml)
                        continue
                    #legendary = ET.SubElement(monster, 'trait')
                    for e in utils.getEntryString(t["entries"],m,args).split("\n"):
                        text = ET.SubElement(legendary, 'text')
                        text.text = e
            if 'mythicEncounter' in l:
                mythic = ET.SubElement(lair, 'trait')
                name = ET.SubElement(mythic, 'name')
                name.text = "{} as a Mythic Encounter".format(m["name"])
                if not args.nohtml:
                    name.text = "<u>{}</u>".format(name.text)
                text = ET.SubElement(legendary, 'text')
                mythic = ET.SubElement(monster, 'legendary')
                for e in utils.getEntryString(l["mythicEncounter"],m,args).split("\n"):
                    text = ET.SubElement(mythic, 'text')
                    text.text = e
            ldescription = ET.SubElement(lair, 'description')
            ldescription.text = ""
            if sourcetext: ldescription.text += "\n\n<b>Source:</b> " + sourcetext.rstrip("123456790") + str(l["page"])
            ldescription.text += "\n<b>Occupant:</b> <a href=\"/monster/" + slug + "\">" + utils.fixTags(m['name'],m,args.nohtml) + "</a>"

def getDesc(f,m,t = 1):
    text = ''
    prevStr = False
    if type(f) != list: return 'not list\n'
    for e in f:
        if type(e) == str:
            if prevStr: text+= '    '
            text += utils.fixTags(e,m) + '\n'
            prevStr = True
        elif type(e) == list:
            prevStr = False
            text = getDesc(e,m,t+1)
        elif type(e) == dict:
            prevStr = False
            if e.get('type') == 'quote': text += '<i>' + getDesc(e['entries'],m,t)[:-1] + '</i>\n'
            elif e.get('name') is not None:
                if t == 1:
                    text += '\n<b><u>' + utils.fixTags(e['name'],m) + '</u></b>\n'
                elif t == 2:
                    text += '\n<b>' + utils.fixTags(e['name'],m) + '</b>\n'
                else:
                    text += '<b>' + utils.fixTags(e['name'],m) + '.</b> '
                text += getDesc(e.get('entries'),m,t+1)
            elif e.get('type') == 'section':
                text += getDesc(e.get('entries'),m,t-1)
            elif e.get('type') == 'entries':
                text += getDesc(e.get('entries'),m,t+1)
            elif e.get('type') == 'inset':
                text += '\n<b><u>' + e.get('name') + '</u></b>' + getDesc(e.get('entries'),m,t+1)
            elif e.get('type') == 'list':
                text += '    ' + getDesc(e.get('items'),m,t+1)
            else:
                text += '\n\nKey Type Error: ' + e.get('type') + '\n\n'
        else:
            text += '\n\nVariable Type Error: ' + type(e) +'\n\n'
    return text