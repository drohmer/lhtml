"""LHTML command-line interface.

Usage:
    lhtml [-w] file.l.html                       # Single file → stdout
    lhtml [-w] file.l.html -o output.html         # Single file → output file
    lhtml [-w] a.l.html b.l.html                  # Multiple files → .html next to sources
    lhtml [-w] a.l.html b.l.html -o build/        # Multiple files → output directory
    python -m lhtml [same options]
"""

import os
import argparse

from .pipeline import ProcessingPipeline


_pipeline = ProcessingPipeline()


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


def _process_file(f_in, meta_base):
    """Process a single LHTML file and return the HTML output."""
    meta = dict(meta_base)
    dir_to_include = os.path.dirname(os.path.abspath(f_in))
    if dir_to_include:
        meta['directory_include'] = meta.get('directory_include', []) + [dir_to_include + '/']

    with open(f_in) as fid:
        txt = _ensure_trailing_newline(fid.read())

    return _ensure_trailing_newline(_pipeline.run(txt, meta))


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description='Lightweight HTML')
    parser.add_argument('inputFiles', nargs='+', help='Input file(s)')
    parser.add_argument('-w', '--wrapAuto',
                        help='Wrap content in basic HTML template',
                        action='store_true')
    parser.add_argument('-o', '--output',
                        help='Output file (single input) or directory (multiple inputs)')
    args = parser.parse_args()

    meta = {'directory_include': [os.getcwd() + '/']}
    if args.wrapAuto:
        meta['wrap-auto'] = True

    single_file = len(args.inputFiles) == 1
    single_to_stdout = single_file and args.output is None

    for f_in in args.inputFiles:
        if not os.path.isfile(f_in):
            print(f'Error: file not found [{f_in}]')
            continue

        html = _process_file(f_in, meta)

        if single_to_stdout:
            print(html)
        else:
            out_path = _output_path_for(f_in, args.output)
            with open(out_path, 'w') as f_out:
                f_out.write(html)


if __name__ == '__main__':
    main()
