# -*- coding: utf-8 -*-
#@author: RaNaN

from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import os
import sys
from builtins import COREDIR, object

from future import standard_library

from pyload.utils.pluginloader import LoaderFactory, PluginLoader

standard_library.install_aliases()


class PluginMatcher(object):
    """
    Abstract class that allows modify which plugins to match and to load.
    """

    def match_url(self, url):
        """
        Returns (type, name) of a plugin if a match is found.
        """
        return

    def match_plugin(self, plugin, name):
        """
        Returns (type, name) of the plugin that will be loaded instead.
        """
        return None


class PluginManager(object):
    ROOT = "pyload.plugin"
    LOCALROOT = "userplugins"

    MATCH_HISTORY = 10
    DEFAULT_PLUGIN = "BasePlugin"

    def __init__(self, core):
        self.pyload = core

        # cached modules (type, name)
        self.modules = {}
        # match history to speedup parsing (type, name)
        self.history = []

        # register for import addon
        sys.meta_path.append(self)

        # add to path, so we can import from userplugins
        sys.path.append(os.path.abspath(""))
        self.loader = LoaderFactory(PluginLoader(os.path.abspath(self.LOCALROOT), self.LOCALROOT, self.pyload.config),
                                    PluginLoader(os.path.abspath(os.path.join(COREDIR, "pyload", "plugin")), self.ROOT,
                                                 self.pyload.config))

        self.loader.check_versions()

        # plugin matcher to overwrite some behaviour
        self.matcher = []

    def add_matcher(self, matcher, index=0):
        """
        Inserts matcher at given index, first position by default.
        """
        if not isinstance(matcher, PluginMatcher):
            raise TypeError(
                "Expected type of PluginMatcher, got '{}' instead".format(type(matcher)))

        if matcher in self.matcher:
            self.matcher.remove(matcher)

        self.matcher.insert(index, matcher)

    def remove_matcher(self, matcher):
        """
        Removes a matcher if it exists.
        """
        if matcher in self.matcher:
            self.matcher.remove(matcher)

    def parse_urls(self, urls):
        """
        Parse plugins for given list of urls, separate to crypter and hoster.
        """
        res = {"hoster": [], "crypter": []}  #: tupels of (url, plugin)

        for url in urls:
            if not isinstance(url, str):
                self.pyload.log.debug(
                    "Parsing invalid type {}".format(type(url)))
                continue

            found = False

            # search the history
            for ptype, name in self.history:
                if self.loader.get_plugin(ptype, name).re.match(url):
                    res[ptype].append((url, name))
                    found = (ptype, name)
                    break  #: need to exit this loop first

            if found:  #: found match
                if self.history[0] != found:  #: update history
                    self.history.remove(found)
                    self.history.insert(0, found)
                continue

            # matcher are tried secondly, they won't go to history
            for m in self.matcher:
                match = m.match_url(url)
                if match and match[0] in res:
                    ptype, name = match
                    res[ptype].append((url, name))
                    found = True
                    break

            if found:
                continue

            for type in ("crypter", "hoster"):
                for loader in self.loader:
                    for name, info in loader.get_plugins(type).items():
                        if info.re.match(url):
                            res[type].append((url, name))
                            self.history.insert(0, (type, name))
                            # cut down to size
                            del self.history[self.MATCH_HISTORY:]
                            found = True
                            break
                    if found:
                        break
                if found:
                    break

            if not found:
                res['hoster'].append((url, self.DEFAULT_PLUGIN))

        return res['hoster'], res['crypter']

    def find_type(self, name):
        """
        Finds the type to a plugin name.
        """
        return self.loader.find_type(name)

    def get_plugin(self, type, name):
        """
        Retrieves the plugin tuple for a single plugin or none.
        """
        return self.loader.get_plugin(type, name)

    def get_plugins(self, type):
        """
        Get all plugins of a certain type in a dict.
        """
        plugins = {}
        for loader in self.loader:
            plugins.update(loader.get_plugins(type))
        return plugins

    def get_plugin_class(self, type, name, overwrite=True):
        """
        Gives the plugin class of a hoster or crypter plugin

        :param overwrite: allow the use of overwritten plugins
        """
        if overwrite:
            for m in self.matcher:
                match = m.match_plugin(type, name)
                if match:
                    type, name = match

        return self.load_class(type, name)

    def load_attributes(self, type, name):
        for loader in self.loader:
            if loader.has_plugin(type, name):
                return loader.load_attributes(type, name)

        return {}

    def load_module(self, type, name):
        """
        Returns loaded module for plugin

        :param type: plugin type, subfolder of module.plugins
        """
        if (type, name) in self.modules:
            return self.modules[(type, name)]
        for loader in self.loader:
            if loader.has_plugin(type, name):
                try:
                    module = loader.load_module(type, name)
                    # cache import
                    self.modules[(type, name)] = module
                    return module
                except Exception as e:
                    self.pyload.log.error(
                        _("Error importing {}: {}").format(name, e.message))
                    # self.pyload.print_exc()

    def load_class(self, type, name):
        """
        Returns the class of a plugin with the same name.
        """
        module = self.load_module(type, name)
        try:
            if module:
                return getattr(module, name)
        except AttributeError:
            self.pyload.log.error(
                _("Plugin does not define class '{}'").format(name))

    def find_module(self, fullname, path=None):
        # redirecting imports if necessary
        for loader in self.loader:
            if not fullname.startswith(loader.package):
                continue

            # TODO: not well tested
            offset = 1 - loader.package.count(".")

            split = fullname.split(".")
            if len(split) != 4 - offset:
                return
            type, name = split[2 - offset:4 - offset]

            # check if a different loader than the current one has the plugin
            # in this case import needs redirect
            for l2 in self.loader:
                if l2 is not loader and l2.has_plugin(type, name):
                    return self

        # TODO: Remove when all plugin imports are adapted
        if "module" in fullname:
            return self

    def reload_plugins(self, type_plugins):
        """
        Reloads and reindexes plugins.
        """

        # TODO
        # check if reloadable
        # reload
        # save new plugins
        # update index
        # reload accounts

    def is_user_plugin(self, name):
        """
        A plugin suitable for multiple user.
        """
        return any(l.is_user_plugin(name) for l in self.loader)

    def get_category(self, name):
        plugin = self.loader.get_plugin("addon", name)
        if plugin:
            return plugin.category or "addon"

    def load_icon(self, name):
        """
        Load icon for single plugin, base64 encoded.
        """
        raise NotImplementedError

    def check_dependencies(self, type, name):
        """
        Check deps for given plugin

        :return: List of unfullfilled dependencies
        """
        raise NotImplementedError