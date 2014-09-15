import redis
import time
from bricklayer.model_base import transaction

class BuildInfo:

    def __init__(self, project='', build_id=0):
        self.redis_cli = self.connect()
        self.project = project
        if project and build_id == 0:
            self.build_id = self.redis_cli.incr('build:%s' % project)
            self.redis_cli.rpush('build:%s:list' % project, self.build_id)
            self.redis_cli.set('build:%s:%s:time' % (self.project, self.build_id), time.strftime('%d/%m/%Y %H:%M', time.localtime(time.time())))
        if build_id > 0:
            self.build_id = build_id

    def __dir__(self):
        return []
    
    @transaction
    def time(self, version=''):
        return self.redis_cli.get('build:%s:%s:time' % (self.project, self.build_id))

    @transaction
    def version(self, version=''):
        if version:
            return self.redis_cli.set('build:%s:%s:version' % (self.project, self.build_id), version) 
        return self.redis_cli.get('build:%s:%s:version' % (self.project, self.build_id))

    @transaction
    def release(self, release=''):
        if release:
            return self.redis_cli.set('build:%s:%s:release' % (self.project, self.build_id), release) 
        return self.redis_cli.get('build:%s:%s:release' % (self.project, self.build_id))


    @transaction
    def log(self, logfile=''):
        if logfile:
            return self.redis_cli.set('build:%s:%s:log' % (self.project, self.build_id), logfile) 
        return self.redis_cli.get('build:%s:%s:log' % (self.project, self.build_id))

    @transaction
    def builds(self):
        builds = self.redis_cli.lrange('build:%s:list' % self.project, 0, self.redis_cli.llen('build:%s:list' % self.project))
        return builds

    @transaction
    def building(self, is_building=None):
        if is_building != None:
            if is_building:
                self.redis_cli.incr('build:%s:%s:status' % (self.project, self.build_id))
            else:
                self.redis_cli.decr('build:%s:%s:status' % (self.project, self.build_id))
            return is_building
        else:
            if self.redis_cli.get('build:%s:%s:status' % (self.project, self.build_id)) > 0:
                return True
            else:
                return False

    def connect(self):
        return redis.Redis()    
