#!/usr/bin/env python

# Copyright (c) 2015 Ingo Dyck <bogus@bogushome.net>
#
# Permission to use, copy, modify, and distribute this software for any
# purpose with or without fee is hereby granted, provided that the above
# copyright notice and this permission notice appear in all copies.
#
# THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
# WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
# MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
# ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
# WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
# ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
# OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.

import json
import time
import threading
import sys
import collectd
import string
from docker import Client

TERMINATE=False
docker_client = None
collector_dict = {}
config = {}

class YourFormatter(string.Formatter):
    def get_value(self, field_name, args, kwargs):
        return kwargs.get(field_name, '')

    def get_field(self, field_name, args, kwargs):
        first, rest = field_name._formatter_field_name_split()
        obj = self.get_value(first, args, kwargs)

        for is_attr, i in rest:
            if is_attr:
                obj = getattr(obj, i)
            else:
                if isinstance(obj, list) and i.endswith("="):
                    obj_new = None
                    for item in obj:
                        if item.startswith(i):
                            obj_new = item.partition('=')[2]
                            break
                    obj = obj_new
                else:
                    obj = obj.get(i, '')
        return obj, first

class Collector(threading.Thread):
    def run(self):
        stats_stream = docker_client.stats(self.container_id)
        for stat in stats_stream:
            if TERMINATE:
                return
            self.stat_obj = json.loads(stat.decode('utf-8'))

    def __init__(self, container_id):
        self.container_id = container_id
        self.stat_obj = None
        self.metric_prefix=container_id
        if config.has_key('CustomPath'):
            inspect_obj = docker_client.inspect_container(self.container_id)
            fmt = YourFormatter()
            self.metric_prefix=fmt.format(config['CustomPath'], **inspect_obj)
            del(fmt)
        threading.Thread.__init__(self)

def getKey(haystack, needle):
    needle_path = needle.partition('.')
    if needle == needle_path[0]:
        if isinstance(haystack, list):
            needle = int(needle)
        return haystack[needle]
    else:
        return getKey(haystack[needle_path[0]], needle_path[2])

def dispatch_value(stat_obj, key, plugin_instance, values):
    val = collectd.Values(plugin='docker_stats')
    val.type='gauge'
    val.type_instance = key
    val.plugin_instance = plugin_instance
    val.values = values
    if config['Debug']: collectd.info('docker_stats plugin: dispatch_value %s.%s %i' % (plugin_instance, key, val.values[0]))
    val.dispatch()

#blkio_stats have a very peculiar format, so we handle them separately
def get_blkio_stats(cid, key):
    blkio_stats_obj = getKey(collector_dict[cid].stat_obj, key)
    for x in blkio_stats_obj.keys():
        for op in blkio_stats_obj[x]:
            key_tmp = "{}.{}.{}".format(key, x, op['op'])
            dispatch_value(collector_dict[cid].stat_obj, key_tmp, collector_dict[cid].metric_prefix, [op['value']])

def get_stats(cid,key=None):
    if collector_dict[cid].stat_obj:
        if key == None:
            #No key -> we're at top level
            for key in collector_dict[cid].stat_obj.keys():
                if key == 'read':
                    #read key is just a timestamp, no stats here
                    continue
                get_stats(cid,key)
        elif key == "blkio_stats":
            #blkio_stats have a very peculiar format, so we handle them separately
            get_blkio_stats(cid, key)
        else:
            value = getKey(collector_dict[cid].stat_obj, key)
            if isinstance(value, list):
                for i in range(len(value)):
                    key_tmp = "{}.{}".format(key, i)
                    get_stats(cid,key_tmp)
            elif isinstance(value, dict):
                for i in value.keys():
                    key_tmp = "{}.{}".format(key, i)
                    get_stats(cid,key_tmp)
            else:
                dispatch_value(collector_dict[cid].stat_obj, key, collector_dict[cid].metric_prefix, [value])

def maintain_collector_dict():
    global collector_dict
    containers=docker_client.containers()
    sleep_time=0
    for container in containers:
        cid = container["Id"][0:12]
        if cid not in collector_dict:
            if config['Debug']: collectd.info('docker_stats plugin: init container %s' % cid )
            collector_dict[cid] = Collector(cid)
            collector_dict[cid].start()
            #it takes about 1sec for a newly started Collector thread to get initial stats
            sleep_time=1
    #cleanup orphaned entries
    for cid in collector_dict.keys():
        if not collector_dict[cid].is_alive():
            if config['Debug']: collectd.info('docker_stats plugin: read.cleanup container %s' % cid )
            del collector_dict[cid]

    time.sleep(sleep_time)

def read_callback():
    maintain_collector_dict()
    for cid in collector_dict.keys():
        if config['Debug']: collectd.info('docker_stats plugin: read container %s' % cid )
        get_stats(cid)

def shutdown_callback():
    global TERMINATE
    TERMINATE=True

def init_callback():
    global docker_client
    if config['Debug']: collectd.info('docker_stats plugin: init')
    docker_client = Client(base_url=config['BaseURL'])
    maintain_collector_dict()

def config_callback(conf):
    global config

    #set some defaults
    config['BaseURL'] = 'unix://var/run/docker.sock'
    config['Debug'] = False

    for node in conf.children:
        config[node.key] = node.values[0]

    if config['Debug']: collectd.info('docker_stats config: %s' % (config))


collectd.register_config(config_callback)
collectd.register_init(init_callback)
collectd.register_read(read_callback)
collectd.register_shutdown(shutdown_callback)

# vim: tabstop=8 expandtab shiftwidth=4 softtabstop=4 autoindent
