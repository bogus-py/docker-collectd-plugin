# docker-collectd-plugin

This plugin just grabs all metrics it gets from "docker stats".

### Install

docker_stats.py uses the docker stats API, so we require:

- docker >= 1.5
- docker-py >= 1.0.0

```
# pip install docker-py
# cp docker_stats.py /usr/share/collectd/plugins
# cat >> /etc/collectd/conf.d/docker_stats << EOF
<LoadPlugin python>
  Globals true
</LoadPlugin>
<Plugin python>
  ModulePath "/usr/share/collectd/plugins"
  Import "docker_stats"
  <Module "docker_stats">
    #CustomPath "{Config[Env][MARATHON_APP_ID=]}.{Config[Hostname]}"
    #BaseURL "unix://var/run/docker.sock"
    #Debug true
  </Module>
</Plugin>
EOF
```

### Config Options
#### CustomPath
Here you can reference almost any element from docker inspect output. The exception are array elements, and the exception here is the list if ENV variables (or any list of elements containing strings with a "foo=bar" pattern). Let's clear things up with an example:

```
{
    "Config": {
        "Env": [
            "MARATHON_APP_ID=/foo-service"
        ],
        "Hostname": "0b5432180f59"
}

"{Config[Env][MARATHON_APP_ID=]}.{Config[Hostname]}" => "/foo-service.0b5432180f59"
```

(Default is short conainer id)

#### BaseURL
#### Debug

### Considerations
**type:**
To keep things simple and since the setup this was initially developed for didn't require any different type is always **gauge**
