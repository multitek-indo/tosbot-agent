"""Regression for settings rows.join and sidebar assets (Node optional)."""
from pathlib import Path
import shutil
import subprocess
import pytest

ROOT=Path(__file__).resolve().parents[1]


def test_sidebar_markup_styles_and_assets():
    page=(ROOT/'app/static/index.html').read_text()
    js=(ROOT/'app/static/app.js').read_text()
    css=(ROOT/'app/static/style.css').read_text()
    assert 'id="app-layout"' in page
    assert 'id="sidebar-backdrop"' in page
    assert 'id="menu-toggle"' in page
    assert 'sidebar-pinned' in js
    assert 'function initSidebar()' in js
    assert '.sidebar:hover' in css
    assert '@media (max-width:760px)' in css
    assert '0.3.0' in page and '0.3.0' in (ROOT/'VERSION').read_text()


def test_settings_render_js_array_contract(tmp_path):
    if not shutil.which('node'):
        pytest.skip('Node.js is optional; browser test was performed at packaging time')
    probe=tmp_path/'probe.cjs'
    probe.write_text('''const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[2],'utf8');
let count=-1,view={innerHTML:''};
const ctx={
 $:()=>view, document:{addEventListener:()=>{}},
 api:async path=>path==='/settings/company'?{company_name:'PT UJI',has_logo:false}:{users:[{name:'admin',updated:0},{name:'staff',updated:0}],current:'admin'},
 esc:x=>String(x),ts:()=>'-',pageHeader:()=>'<h1>Pengaturan</h1>',
 tableInner:(headers,rows)=>{assert(Array.isArray(rows),'tableInner requires an array');count=rows.length;return rows.join('')},
 Date,Promise,Error,console
};
vm.createContext(ctx);vm.runInContext(source,ctx);
ctx.showSettings().then(()=>{assert.equal(count,2);assert(view.innerHTML.includes('staff'));assert(view.innerHTML.includes('Logo dashboard'));console.log('OK')}).catch(e=>{console.error(e);process.exit(1)});
''')
    run=subprocess.run(['node',str(probe),str(ROOT/'app/static/settings.js')],capture_output=True,text=True,timeout=8)
    assert run.returncode==0,run.stdout+run.stderr
