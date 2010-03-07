# -*- coding: utf-8 -*-
"""

    @author: Fabio Erculiani <lxnay@sabayon.org>
    @contact: lxnay@sabayon.org
    @copyright: Fabio Erculiani
    @license: GPL-2

    B{Entropy Package Manager Client Miscellaneous Interface}.

"""

import os
import sys
import shutil
import subprocess
from entropy.client.interfaces import Client
from entropy.exceptions import *
from entropy.const import etpConst, const_convert_to_rawstring
from entropy.output import darkred, darkgreen, red, brown, blue
from entropy.tools import getstatusoutput
from entropy.i18n import _

class FileUpdates:

    CACHE_ID = "conf/scanfs"

    def __init__(self, EquoInstance):
        if not isinstance(EquoInstance, Client):
            mytxt = "A valid Client instance or subclass is needed"
            raise AttributeError(mytxt)
        self.Entropy = EquoInstance
        from entropy.cache import EntropyCacher
        from entropy.core.settings.base import SystemSettings
        self.Cacher = EntropyCacher()
        self.SystemSettings = SystemSettings()
        self.scandata = None

    def merge_file(self, key):
        self.scanfs(dcache = True)
        self.do_backup(key)
        source_file = etpConst['systemroot'] + self.scandata[key]['source']
        dest_file = etpConst['systemroot'] + self.scandata[key]['destination']
        if os.access(source_file, os.R_OK):
            shutil.move(source_file, dest_file)
        self.remove_from_cache(key)

    def remove_file(self, key):
        self.scanfs(dcache = True)
        source_file = etpConst['systemroot'] + self.scandata[key]['source']
        if os.path.isfile(source_file) and os.access(source_file, os.W_OK):
            os.remove(source_file)
        self.remove_from_cache(key)

    def do_backup(self, key):
        self.scanfs(dcache = True)
        sys_set_plg_id = \
            etpConst['system_settings_plugins_ids']['client_plugin']
        files_backup = self.Entropy.SystemSettings[sys_set_plg_id]['misc']['filesbackup']
        dest_file = etpConst['systemroot'] + self.scandata[key]['destination']
        if files_backup and os.path.isfile(dest_file):
            bcount = 0
            backupfile = etpConst['systemroot'] + \
                os.path.dirname(self.scandata[key]['destination']) + \
                "/._entropy_backup." + str(bcount) + "_" + \
                os.path.basename(self.scandata[key]['destination'])
            while os.path.lexists(backupfile):
                bcount += 1
                backupfile = etpConst['systemroot'] + \
                os.path.dirname(self.scandata[key]['destination']) + \
                "/._entropy_backup." + str(bcount) + "_" + \
                os.path.basename(self.scandata[key]['destination'])
            try:
                shutil.copy2(dest_file, backupfile)
            except IOError:
                pass

    def scanfs(self, dcache = True, quiet = False):

        if dcache:

            if self.scandata != None:
                return self.scandata

            # can we load cache?
            try:
                z = self.load_cache()
                if z != None:
                    self.scandata = z
                    return self.scandata
            except (CacheCorruptionError, KeyError, IOError, OSError,):
                pass

        scandata = {}
        counter = 0
        name_cache = set()
        client_conf_protect = self.Entropy.get_system_config_protect()

        for path in client_conf_protect:

            # this avoids encoding issues hands down
            try:
                path = path.encode('utf-8')
            except (UnicodeEncodeError,):
                path = path.encode(sys.getfilesystemencoding())
            # it's a file?
            scanfile = False
            if os.path.isfile(path):
                # find inside basename
                path = os.path.dirname(path)
                scanfile = True

            for currentdir, subdirs, files in os.walk(path):
                for item in files:

                    if scanfile:
                        if path != item:
                            continue

                    filepath = os.path.join(currentdir, item)
                    # FIXME: with Python 3.x we can remove const_convert...
                    # and not use path.encode('utf-8')
                    if item.startswith(const_convert_to_rawstring("._cfg")): 

                        # further check then
                        number = item[5:9]
                        try:
                            int(number)
                        except ValueError:
                            continue # not a valid etc-update file
                        if item[9] != "_": # no valid format provided
                            continue

                        if filepath in name_cache:
                            continue # skip, already done
                        name_cache.add(filepath)

                        mydict = self.generate_dict(filepath)
                        if mydict['automerge']:
                            if not quiet:
                                mytxt = _("Automerging file")
                                self.Entropy.output(
                                    darkred("%s: %s") % (
                                        mytxt,
                                        darkgreen(etpConst['systemroot'] + mydict['source']),
                                    ),
                                    importance = 0,
                                    type = "info"
                                )
                            if os.path.isfile(etpConst['systemroot']+mydict['source']):
                                try:
                                    os.rename(etpConst['systemroot']+mydict['source'],
                                        etpConst['systemroot']+mydict['destination'])
                                except (OSError, IOError,) as e:
                                    if not quiet:
                                        mytxt = "%s :: %s: %s. %s: %s" % (
                                            red(_("System Error")),
                                            red(_("Cannot automerge file")),
                                            brown(etpConst['systemroot'] + mydict['source']),
                                            blue("error"),
                                            e,
                                        )
                                        self.Entropy.output(
                                            mytxt,
                                            importance = 1,
                                            type = "warning"
                                        )
                            continue
                        else:
                            counter += 1
                            scandata[counter] = mydict.copy()

                        if not quiet:
                            try:
                                self.Entropy.output(
                                    "("+blue(str(counter))+") " + \
                                    red(" file: ") + \
                                    os.path.dirname(filepath) + "/" + \
                                    os.path.basename(filepath)[10:],
                                    importance = 1,
                                    type = "info"
                                )
                            except (UnicodeEncodeError, UnicodeDecodeError):
                                pass # possible encoding issues
        # store data
        self.Cacher.push(FileUpdates.CACHE_ID, scandata)
        self.scandata = scandata.copy()
        return scandata

    def load_cache(self):
        sd = self.Cacher.pop(FileUpdates.CACHE_ID)
        if not isinstance(sd, dict):
            raise CacheCorruptionError("CacheCorruptionError")
        # quick test if data is reliable
        try:
            name_cache = set()

            for x in sd:
                mysource = sd[x]['source']
                # filter dupies
                if mysource in name_cache:
                    sd.pop(x)
                    continue
                if not os.path.isfile(etpConst['systemroot']+mysource):
                    raise CacheCorruptionError("CacheCorruptionError")
                name_cache.add(mysource)

            return sd
        except (KeyError, EOFError, IOError,):
            raise CacheCorruptionError("CacheCorruptionError")

    def add_to_cache(self, filepath, quiet = False):
        self.scanfs(dcache = True, quiet = quiet)
        keys = list(self.scandata.keys())
        try:
            for key in keys:
                if self.scandata[key]['source'] == filepath[len(etpConst['systemroot']):]:
                    del self.scandata[key]
        except:
            pass
        # get next counter
        if keys:
            keys = sorted(keys)
            index = keys[-1]
        else:
            index = 0
        index += 1
        mydata = self.generate_dict(filepath)
        self.scandata[index] = mydata.copy()
        self.Cacher.push(FileUpdates.CACHE_ID, self.scandata)

    def remove_from_cache(self, key):
        self.scanfs(dcache = True)
        try:
            del self.scandata[key]
        except:
            pass
        self.Cacher.push(FileUpdates.CACHE_ID, self.scandata)
        return self.scandata

    def generate_dict(self, filepath):

        item = os.path.basename(filepath)
        currentdir = os.path.dirname(filepath)
        tofile = item[10:]
        number = item[5:9]
        try:
            int(number)
        except ValueError:
            raise ValueError("invalid config file number '0000->9999'.")
        tofilepath = currentdir+"/"+tofile
        mydict = {}
        mydict['revision'] = number
        mydict['destination'] = tofilepath[len(etpConst['systemroot']):]
        mydict['source'] = filepath[len(etpConst['systemroot']):]
        mydict['automerge'] = False
        if not os.path.isfile(tofilepath):
            mydict['automerge'] = True
        if (not mydict['automerge']):
            # is it trivial?
            try:
                if not os.path.lexists(filepath): # if file does not even exist
                    return mydict
                if os.path.islink(filepath):
                    # if it's broken, skip diff and automerge
                    if not os.path.exists(filepath):
                        return mydict
                result = getstatusoutput('diff -Nua "%s" "%s" | grep "^[+-][^+-]" | grep -v \'# .Header:.*\'' % (filepath, tofilepath,))[1]
                if not result:
                    mydict['automerge'] = True
            except:
                pass
            # another test
            if not mydict['automerge']:
                try:
                    # if file does not even exist
                    if not os.path.lexists(filepath):
                        return mydict
                    if os.path.islink(filepath):
                        # if it's broken, skip diff and automerge
                        if not os.path.exists(filepath):
                            return mydict
                    result = subprocess.call('diff -Bbua "%s" "%s" | egrep \'^[+-]\' | egrep -v \'^[+-][\t ]*#|^--- |^\+\+\+ \' | egrep -qv \'^[-+][\t ]*$\'' % (filepath, tofilepath,), shell = True)
                    if result == 1:
                        mydict['automerge'] = True
                except:
                    pass
        return mydict
