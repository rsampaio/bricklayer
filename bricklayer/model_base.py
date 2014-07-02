import redis

def transaction(method):
    def new(*args, **kwargs):
        args[0].redis_cli = redis.Redis()
        try:
            ret = method(*args, **kwargs)
            if ret == None:
                ret = ""
            return ret
        finally:
            if (hasattr(args[0].redis_cli, "connection")):
                args[0].redis_cli.connection.disconnect()
            if (hasattr(args[0].redis_cli.connection_pool, "disconnect")):
                args[0].redis_cli.connection_pool.disconnect()
    return new

class ModelBase:
    
    redis_cli = None
    namespace = ''

    def connect(self):
        return redis.Redis()

    @transaction
    def save(self):
        data = {}
        for attr in self.__dir__():
            data[attr] = getattr(self, attr)
        self.redis_cli.hmset("%s:%s" % (self.namespace, self.name), data)
        self.populate(self.name)
    
    @transaction
    def populate(self, name):
        res = self.redis_cli.hgetall("%s:%s" % (self.namespace, name))
        for key, val in res.iteritems():
            key = key.replace('%s:' % self.namespace, '')
            setattr(self, key, val)

    @transaction
    def exists(self):
        res = self.redis_cli.exists('%s:%s' % (self.namespace, self.name))
        return res

    @transaction
    def delete(self):
        project_keys = self.redis_cli.keys("*:%s" % self.name)
        for key in project_keys:
            self.redis_cli.delete(key)

        project_keys = self.redis_cli.keys("*:%s:*" % self.name)
        for key in project_keys:
            self.redis_cli.delete(key)
