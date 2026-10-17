"""LHTML command-line interface.

Each problem is one line on stderr, `file:line:column: level: message`.

Usage:
    lhtml [-w] file.l.html                       # Single file → stdout
    lhtml [-w] file.l.html -o output.html         # Single file → output file
    lhtml [-w] a.l.html b.l.html                  # Multiple files → .html next to sources
    lhtml [-w] a.l.html b.l.html -o build/        # Multiple files → output directory
    lhtml -b file.l.html                          # Source line breaks rendered as <br>
    lhtml -m macros.yaml file.l.html              # Custom :: tags declared in a YAML file
    lhtml --version
    python -m lhtml [same options]
"""

import os
import sys
import argparse
import warnings

from . import __version__
from .errors import LHTMLError
from .macros import load_macros, registry_with_macros
from .pipeline import run
from .process import read_source


def _ensure_trailing_newline(text):
    if text and text[-1] != '\n':
        return text + '\n'
    return text


def _output_path_for(input_path, output_arg):
    """Determine the output path for a given input file.

    If output_arg is a directory, write <dir>/<basename>.html.
    If output_arg is a file path, return it directly (single-file mode).
    If output_arg is None, derive .html from the input path.
    """
    basename = os.path.basename(input_path)
    name, _ = os.path.splitext(basename)
    # Strip double extensions like .l.html → .html
    if name.endswith('.l'):
        name = name[:-2]

    if output_arg is None:
        # Write next to source
        return os.path.join(os.path.dirname(input_path), name + '.html')

    if os.path.isdir(output_arg) or output_arg.endswith('/'):
        os.makedirs(output_arg, exist_ok=True)
        return os.path.join(output_arg, name + '.html')

    # Treat as a direct file path (single-file mode)
    return output_arg


def diagnostic(path, level, problem):
    """`path:line:column: level: message`, the place as far as it is known."""
    place = ':'.join(str(n) for n in (getattr(problem, 'line', None), getattr(problem, 'column', None))
                     if n is not None)
    return f"{path}{':' + place if place else ''}: {level}: {problem}"


def _process_file(f_in, meta_base):
    """Process a single LHTML file and return (html, warnings)."""
    meta = dict(meta_base)
    meta['current_directory'] = os.path.dirname(os.path.abspath(f_in)) + '/'

    txt = _ensure_trailing_newline(read_source(f_in))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter('always')
        html = _ensure_trailing_newline(run(txt, meta))
    return html, sorted((w.message for w in caught),       # in the order of the file
                        key=lambda m: (getattr(m, 'line', None) or 0, getattr(m, 'column', None) or 0))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Lightweight HTML')
    parser.add_argument('input', nargs='+', help='Input file(s)')
    parser.add_argument('-w', '--wrap',
                        help='Wrap content in basic HTML template',
                        action='store_true')
    parser.add_argument('-b', '--line-breaks',
                        help='Render the line breaks of the source text as <br>',
                        action='store_true')
    parser.add_argument('-m', '--macros', action='append', metavar='FILE',
                        help='YAML file of macros (custom :: tags); may be repeated')
    parser.add_argument('-o', '--output',
                        help='Output file (single input) or directory (multiple inputs)')
    parser.add_argument('-V', '--version', action='version',
                        version=f'lhtml {__version__}')
    args = parser.parse_args()

    meta = {}
    if args.wrap:
        meta['wrap-auto'] = True
    if args.line_breaks:
        meta['line-breaks'] = True
    if args.macros:
        try:
            meta['macros'] = load_macros([os.path.abspath(f) for f in args.macros])
            registry_with_macros(meta['macros'])  # validate before processing files
        except LHTMLError as e:
            print(diagnostic(args.macros[0] if len(args.macros) == 1 else 'lhtml', 'error', e), file=sys.stderr)
            sys.exit(1)

    single_file = len(args.input) == 1
    single_to_stdout = single_file and args.output is None

    if (not single_file and args.output is not None
            and not os.path.isdir(args.output) and not args.output.endswith('/')):
        parser.error(f'-o must be a directory when several input files are given '
                     f'(got {args.output!r}; add a trailing / to create it)')

    if not single_to_stdout:            # every output before any is written
        # compared without case: two names differing by case are one file on
        # macOS and Windows; an input missing, or given twice, is not a collision
        written, inputs, seen = {}, {os.path.realpath(f) for f in args.input}, set()
        for f_in in args.input:
            if not os.path.isfile(f_in) or os.path.realpath(f_in) in seen:
                continue
            seen.add(os.path.realpath(f_in))
            out_path = os.path.realpath(_output_path_for(f_in, args.output))
            if out_path in inputs:      # an input it would overwrite: refused for that file below
                continue
            out_path = out_path.casefold()
            if out_path in written:
                print(f'lhtml: error: {written[out_path]} and {f_in} would both be written to '
                      f'{_output_path_for(f_in, args.output)}: nothing written', file=sys.stderr)
                sys.exit(1)
            written[out_path] = f_in

    errors = 0
    for f_in in args.input:
        if not os.path.isfile(f_in):
            print(f'{f_in}: error: file not found', file=sys.stderr)
            errors += 1
            continue

        try:
            html, messages = _process_file(f_in, meta)
            for warning in messages:
                print(diagnostic(f_in, 'warning', warning), file=sys.stderr)

            if single_to_stdout:
                sys.stdout.buffer.write(html.encode('utf-8'))
                sys.stdout.flush()
                continue

            out_path = _output_path_for(f_in, args.output)
            if any(os.path.realpath(out_path) == os.path.realpath(source)
                   or (os.path.exists(out_path) and os.path.exists(source)
                       and os.path.samefile(out_path, source))
                   for source in args.input):
                raise ValueError(f'output file would overwrite the input file [{out_path}]')
            out_dir = os.path.dirname(out_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            with open(out_path, 'w', encoding='utf-8', newline='') as f_out:
                f_out.write(html)
        except (LHTMLError, OSError, UnicodeError, ValueError) as e:
            print(diagnostic(f_in, 'error', e), file=sys.stderr)
            errors += 1

    if errors:
        sys.exit(1)


if __name__ == '__main__':
    main()
