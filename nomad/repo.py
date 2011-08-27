import os, os.path as op
from datetime import datetime
from ConfigParser import ConfigParser, NoOptionError

from nomad.utils import cachedproperty


raiseexception = object()


class Repository(object):
    DEFAULTS = {
        'nomad.table': 'nomad',
        'nomad.env': 'default',
        }

    def __init__(self, confpath, overrides=None):
        self.conf = ConfigParser()
        if not self.conf.read(confpath):
            raise IOError('configuration file %r not found' % confpath)

        for k, v in (overrides or {}).iteritems():
            section, key = k.split('.')
            self.conf.set(section, key, v)

        self.path = self.get('nomad.path', op.dirname(confpath) or '.')

        enginepath = self.fromenv('engine')
        if not '.' in enginepath:
            enginepath = 'nomad.engine.' + enginepath
        enginemod = __import__(enginepath, {}, {}, [''])
        self.engine = getattr(enginemod, 'engine')(self.fromenv('url'))

    def __repr__(self):
        return '<%s: %s>' % (type(self).__name__, self.path)

    def get(self, path, default=raiseexception):
        try:
            return self.conf.get(*path.split('.'))
        except NoOptionError:
            # NOTE: maybe if default is supplied, it should override
            # self.DEFAULTS? Not sure, probably not
            if path in self.DEFAULTS:
                return self.DEFAULTS[path]

            if default is raiseexception:
                raise
            return default

    def fromenv(self, key):
        return self.conf.get(self.get('nomad.env'), key)

    # actual work done here

    def init_db(self):
        return self.engine.query('''CREATE TABLE %s (
            name varchar(255) NOT NULL,
            date datetime NOT NULL
        )''' % self.get('nomad.table'))

    @cachedproperty
    def available(self):
        migrations = [x for x in os.listdir(self.path) if
                      op.isdir(op.join(self.path, x))]
        return list(sorted(migrations))

    @cachedproperty
    def applied(self):
        return [x for x, in
                self.engine.query('SELECT name FROM %s ORDER BY date' %
                                  self.get('nomad.table'))]

    def up(self, name):
        m = Migration(self, name)
        m.up()

    def down(self, name):
        m = Migration(self, name)
        m.down()


class Migration(object):
    def __init__(self, repo, name):
        self.repo = repo
        self.name = name

    def __repr__(self):
        return '<%s: %s>' % (type(self).__name__, self.name)

    @property
    def path(self):
        return op.join(self.repo.path, self.name)

    def up(self):
        print 'applying upgrade %s' % self
        with file(op.join(self.path, 'up.sql')) as f:
            self.repo.engine.query(f.read())
        self.repo.engine.query('INSERT INTO %s (name, date) VALUES (?, ?)'
                               % self.repo.get('nomad.table'),
                               self.name, datetime.now())

    def down(self):
        print 'applying downgrade %s' % self
        with file(op.join(self.path, 'down.sql')) as f:
            self.repo.engine.query(f.read())
        self.repo.engine.query('DELETE FROM %s WHERE name = ?'
                               % self.repo.get('nomad.table'),
                               self.name)
