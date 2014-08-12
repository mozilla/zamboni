import tempfile

from nose.tools import eq_

from amo.utils import walkfiles


def test_walkfiles():
    basedir = tempfile.mkdtemp()
    subdir = tempfile.mkdtemp(dir=basedir)
    file1, file1path = tempfile.mkstemp(dir=basedir, suffix='_foo')
    file2, file2path = tempfile.mkstemp(dir=subdir, suffix='_foo')
    file3, file3path = tempfile.mkstemp(dir=subdir, suffix='_bar')

    eq_(list(walkfiles(basedir, suffix='_foo')), [file1path, file2path])
    eq_(list(walkfiles(basedir)), [file1path, file2path, file3path])
