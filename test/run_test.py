import sys
import os
from colors import * #pip3 install ansicolors

sys.path.append('../src/')
import lhtml

def find_test_files(root):
    all_files = os.listdir(root)
    all_files_set = set(all_files)

    test_files = []
    for f in all_files:
        if f.endswith('.l.html'):
            f_reference = f.replace('.l.html','-out.html')
            if f_reference in all_files_set:
                test_files.append((f,f_reference))
    return test_files


test_dir = 'input_tests/'
test_files = find_test_files(test_dir)

print(f'Test files from {test_dir}')
meta = {'directory_include':[os.getcwd()+'/'+test_dir]}

for f,f_ref in test_files:
    path_in = test_dir+f
    path_ref = test_dir+f_ref
    
    meta_current = dict(meta)

    with open(path_in) as fid:
        with open(path_ref) as fid_ref:
            txt = fid.read()
            txt_ref = fid_ref.read()

            is_wrap = f.endswith('.w.l.html')
            if is_wrap:
                meta_current['wrap-auto']=True

            html_out = lhtml.run(txt, meta_current)

            is_same = txt_ref[:-1]==html_out

            if is_same==True:
                print('\t['+color('OK',fg='green')+']'+f'- {path_in}')
            else:
                print('\t['+color('KO',fg='red')+']'+f'- {path_in}')
