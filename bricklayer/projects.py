import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), 'utils'))
from threading import Lock
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.pool import SingletonThreadPool
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base

from config import BrickConfig

Base = declarative_base()

_session_lock = Lock()

def synchronized(lock):
    def wrapper(func):
        def locked(*args, **kargs):
            try:
                lock.acquire()
                try:
                    return func(*args, **kargs)
                except Exception, e:
                    raise
            finally:
                lock.release()

        return locked
            
    return wrapper

class Session:

    _engine = None
    _session_maker = scoped_session(sessionmaker())

    def __init__(self):
        self._engine = create_engine(BrickConfig().get('databases', 'uri'), 
                                     poolclass=SingletonThreadPool)
        self._session_maker.configure(bind=self._engine)
        self._session = self._session_maker()

    def get(self):
        return self._session

    @classmethod
    def get_engine(self):
        return self._engine


class Projects(Base):
    __tablename__ = 'projects'

    id = Column(Integer, primary_key=True)
    name = Column(String)
    git_url = Column(String)
    build_cmd = Column(String)
    install_cmd = Column(String)
    install_prefix = Column(String)
    last_tag = Column(Integer)
    last_commit = Column(String)
    username = Column(String)
    email = Column(String)
    repository_url = Column(String)
    version = Column(String)
    release = Column(String)
    branch = Column(String, default='master')

    def __init__(self, name='', git_url='', install_cmd='', version=''):
        self.name = name
        self.git_url = git_url
        self.install_cmd = install_cmd
        self.version = version
        self.email = 'bricklayer@locaweb.com.br'
        self.username = 'Bricklayer Builder'
    
    def __repr__(self):
        return "<Project name='%s' id=%s>" % (self.name, self.id)
    
    @classmethod
    @synchronized(_session_lock)
    def get(self, name):
        result = Session().get().query(Projects).filter_by(name=name)[0]
        return result
    
    @classmethod
    @synchronized(_session_lock)
    def get_all(self):
        for project in Session().get().query(Projects):
            yield project
        
    @synchronized(_session_lock)
    def save(self):
        Session().get().add(self)
        Session().get().commit()
    
    @synchronized(_session_lock)
    def delete(self):
        Session().get().delete(self)
        Session().get().commit()

    def create_table(self, engine):
        print engine
        self.metadata.create_all(engine)
    
if __name__ == '__main__':
    BrickConfig('/etc/bricklayer/bricklayer.ini')

    _engine = create_engine(BrickConfig().get('databases', 'uri'), 
                                     poolclass=SingletonThreadPool)
    projects_db = Projects()
    projects_db.create_table(_engine)
