"""The diagnostics: what a stream cannot write is escaped, never lost."""

import io
import os

import pytest

from lhtml import cli
from lhtml.diagnostics import Diagnostic, Reporter, shown_path


def _ascii_stream():
    raw = io.BytesIO()
    return raw, io.TextIOWrapper(raw, encoding='ascii')


@pytest.mark.parametrize('rich', [False, True])
def test_an_accent_on_an_ascii_stream_is_escaped(rich):
    raw, stream = _ascii_stream()
    reporter = Reporter(stream, rich=rich, color=False)
    reporter.report(Diagnostic('été.l.html', 'error', 'problème ici', 1, 3), 'déjà vu\n')
    reporter.report(Diagnostic('b.l.html', 'warning', 'second'))
    stream.flush()
    shown = raw.getvalue().decode('ascii')
    assert '\\xe9t\\xe9.l.html:1:3: error: probl\\xe8me ici' in shown
    assert 'b.l.html: warning: second' in shown     # the next one is shown too
    assert reporter.stream is stream


def test_utf8_streams_are_written_as_they_are():
    stream = io.StringIO()
    Reporter(stream, rich=False, color=False).report(Diagnostic('été.l.html', 'error', 'problème'))
    assert stream.getvalue() == 'été.l.html: error: problème\n'


def test_a_stream_that_cannot_encode_what_it_did_not_declare():
    class Latin(io.StringIO):           # declares no encoding, writes ASCII only
        def write(self, text):
            text.encode('ascii')
            return super().write(text)
    stream = Latin()
    Reporter(stream, rich=False, color=False).report(Diagnostic('é', 'error', 'x'))
    assert stream.getvalue() == '\\xe9: error: x\n'


def test_a_closed_stream_stops_the_writes_not_the_run():
    stream = io.StringIO()
    stream.close()
    reporter = Reporter(stream, rich=False, color=False)
    reporter.report(Diagnostic('a', 'error', 'x'))
    reporter.report(Diagnostic('b', 'error', 'y'))
    assert reporter.stream is None and reporter.counts['error'] == 2


def test_a_path_on_another_drive_stays_absolute(monkeypatch):
    def relpath(path, start=None):
        raise ValueError('path is on mount C:, start on mount D:')
    monkeypatch.setattr(os.path, 'relpath', relpath)
    assert shown_path(os.path.abspath('x.l.html')) == os.path.abspath('x.l.html')


def test_the_exit_code_does_not_depend_on_the_stream(tmp_path, monkeypatch):
    page = tmp_path / 'été.l.html'
    page.write_text('include::missing.html\n', encoding='utf-8')
    codes = []
    for encoding in ('ascii', 'utf-8'):
        raw = io.BytesIO()
        monkeypatch.setattr('sys.stderr', io.TextIOWrapper(raw, encoding=encoding))
        monkeypatch.setattr('sys.stdout', io.StringIO())
        monkeypatch.setattr('sys.argv', ['lhtml', str(page)])
        with pytest.raises(SystemExit) as stop:
            cli.main()
        codes.append(stop.value.code)
        import sys
        sys.stderr.flush()
        assert 'missing.html' in raw.getvalue().decode(encoding)
    assert codes == [1, 1]
