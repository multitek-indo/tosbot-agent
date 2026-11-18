"use strict";
async function refreshBranding(){
 const b=await api('/branding');S.branding=b;
 document.querySelectorAll('.company-name').forEach(el=>el.textContent=b.company_name);
 document.title=b.company_name+' — Operations Hub';
 document.querySelectorAll('.brand-logo').forEach(el=>{
  const img=el.querySelector('.brand-img'),fallback=el.querySelector('.brand-fallback');
  if(!img||!fallback)return;
  if(b.has_logo){img.src=b.logo_url+'?v='+Date.now();img.hidden=false;fallback.hidden=true}
  else{img.hidden=true;fallback.hidden=false;fallback.textContent=b.company_name.charAt(0).toUpperCase()}
 });
 return b;
}
async function showSettings(){
 const [c,us]=await Promise.all([api('/settings/company'),api('/settings/users')]);
 const users=us.users.map(x=>`<tr><td class="primary">${esc(x.name)}</td><td><span class="pill proses">Administrator</span></td><td>${ts(x.updated)}</td><td>${x.name===us.current?'<span class="muted">Akun saat ini</span>':`<button type="button" class="mini-btn" data-action="resetuser" data-username="${esc(x.name)}">Reset password</button> <button type="button" class="mini-btn danger-text" data-action="deleteuser" data-username="${esc(x.name)}">Hapus</button>`}</td></tr>`);
 $('#view').innerHTML=pageHeader('PENGATURAN WORKSPACE','Pengaturan perusahaan','Kelola identitas, logo, akun administrator, dan keamanan dashboard.')+`
 <div class="settings-stack">
  <section class="panel settings-panel"><div class="panel-h"><h2>Identitas perusahaan</h2><small>Ditampilkan di dashboard dan PDF baru</small></div>
   <div class="panel-body"><form id="company-form" class="settings-form"><div class="field"><label for="company-name-input">Nama perusahaan</label><input id="company-name-input" name="name" required minlength="2" maxlength="160" value="${esc(c.company_name)}"></div><button class="btn-primary" type="submit">Simpan nama perusahaan</button></form></div></section>
  <section class="panel settings-panel"><div class="panel-h"><h2>Logo dashboard</h2><small>PNG/JPEG · maksimal 2 MB · optimal 500–1200 px</small></div>
   <div class="panel-body"><div class="settings-logo-row"><div class="logo-preview" id="logo-preview">${c.has_logo?`<img src="${c.logo_url}?v=${Date.now()}" alt="Logo saat ini">`:`<span>${esc(c.company_name.charAt(0))}</span>`}</div><div><p class="settings-note">Logo ini hanya untuk tampilan dashboard (sidebar dan halaman login). Tidak mengubah logo resmi pada penawaran, invoice, atau PDF TosBot.</p>
   <form id="logo-form" class="settings-form"><div class="field"><label for="logo-input">Pilih file gambar</label><input id="logo-input" type="file" accept="image/png,image/jpeg,.png,.jpg,.jpeg" required></div><button class="btn-primary" type="submit">Unggah logo dashboard</button></form></div></div></div></section>
  <section class="panel settings-panel"><div class="panel-h"><h2>Ganti password saya</h2><small>Minimal 10 karakter · sesi akan keluar otomatis</small></div><div class="panel-body">
   <form id="password-form" class="settings-form settings-form-narrow"><div class="form-grid"><div class="field full"><label>Password sekarang</label><input type="password" name="current_password" required autocomplete="current-password"></div><div class="field"><label>Password baru</label><input type="password" name="new_password" required minlength="10" maxlength="256" autocomplete="new-password"></div><div class="field"><label>Ulangi password baru</label><input type="password" name="confirm_password" required minlength="10" maxlength="256" autocomplete="new-password"></div></div><button class="btn-primary" type="submit">Perbarui password</button></form></div></section>
  <section class="panel settings-panel"><div class="panel-h"><h2>Administrator dashboard</h2><small>Semua akun memiliki akses setara admin</small></div>
   <div class="panel-body"><div class="settings-note" style="margin-bottom:16px">Pengguna baru dapat membuka seluruh menu dan mengelola pengguna lain. Demi keamanan, pembuatan akun memerlukan password Anda saat ini.</div>
   <form id="new-user-form" class="settings-form"><div class="form-grid"><div class="field"><label>Username baru</label><input name="username" required minlength="3" maxlength="32" pattern="[a-zA-Z][a-zA-Z0-9._-]{2,31}" placeholder="contoh: teknisi01" autocomplete="off"></div><div class="field"><label>Password pengguna baru</label><input type="password" name="password" minlength="10" maxlength="256" required autocomplete="new-password"></div><div class="field"><label>Konfirmasi password pengguna</label><input type="password" name="confirm_password" minlength="10" maxlength="256" required autocomplete="new-password"></div><div class="field"><label>Password administrator Anda</label><input type="password" name="current_password" required autocomplete="current-password"></div></div><button type="submit" class="btn-primary">+ Tambah administrator</button></form>
   <h3 class="settings-subtitle">Daftar akun aktif</h3>${tableInner(['Pengguna','Hak akses','Password diperbarui','Tindakan'],users)}
  </div></section>
 </div>`;
}
function readFileAsDataURL(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Gagal membaca gambar'));reader.readAsDataURL(file)})}
document.addEventListener('submit',async ev=>{
 const form=ev.target;if(!['company-form','logo-form','password-form','new-user-form'].includes(form.id))return;
 ev.preventDefault();const btn=form.querySelector('button[type=submit]');btn.disabled=true;
 try{
  if(form.id==='company-form'){
   await api('/settings/company','PUT',{name:form.querySelector('[name=name]').value});
   await refreshBranding();message('Nama perusahaan berhasil disimpan');await navigate('settings');
  }else if(form.id==='logo-form'){
   const file=form.querySelector('input[type=file]').files[0];
   if(!file)throw Error('Pilih gambar logo');
   if(!['image/png','image/jpeg'].includes(file.type))throw Error('Gunakan file PNG atau JPEG');
   if(file.size>2_000_000)throw Error('Logo maksimal 2 MB');
   await api('/settings/company/logo','POST',{image:await readFileAsDataURL(file)});
   await refreshBranding();message('Logo dashboard berhasil diperbarui; logo dokumen tidak berubah');await navigate('settings');
  }else if(form.id==='password-form'){
   const f=new FormData(form);if(f.get('new_password')!==f.get('confirm_password'))throw Error('Konfirmasi password tidak sama');
   await api('/settings/password','POST',{current_password:f.get('current_password'),new_password:f.get('new_password')});
   alert('Password berhasil diubah. Silakan masuk kembali dengan password baru.');location.href='/';
  }else if(form.id==='new-user-form'){
   const f=new FormData(form);if(f.get('password')!==f.get('confirm_password'))throw Error('Konfirmasi password pengguna berbeda');
   await api('/settings/users','POST',{username:f.get('username'),password:f.get('password'),current_password:f.get('current_password')});
   message('Administrator baru berhasil ditambahkan');await navigate('settings');
  }
 }catch(e){message(e.message,true)}finally{btn.disabled=false}
});
document.addEventListener('click',e=>{
 const b=e.target.closest('button[data-action]');if(!b)return;
 const name=b.dataset.username;if(!name)return;
 if(b.dataset.action==='resetuser'){
  modal('Reset password: '+esc(name),`<div class="field"><label>Password baru pengguna (minimal 10 karakter)</label><input type="password" name="new_password" required minlength="10" autocomplete="new-password"></div><div class="field"><label>Ulangi password baru</label><input type="password" name="confirm_password" required minlength="10" autocomplete="new-password"></div><div class="field"><label>Password administrator Anda</label><input type="password" name="current_password" required autocomplete="current-password"></div>`,async f=>{
   if(f.get('new_password')!==f.get('confirm_password'))throw Error('Konfirmasi password berbeda');
   await api(`/settings/users/${encodeURIComponent(name)}/password`,'POST',{current_password:f.get('current_password'),new_password:f.get('new_password')});
  });
 }else if(b.dataset.action==='deleteuser'){
  modal('Hapus administrator: '+esc(name),`<p class="settings-note">Pengguna ${esc(name)} akan kehilangan akses. Sesi aktif pengguna tersebut akan dicabut.</p><div class="field"><label>Password administrator Anda untuk konfirmasi</label><input type="password" name="current_password" required autocomplete="current-password"></div>`,async f=>{
   await api(`/settings/users/${encodeURIComponent(name)}/delete`,'POST',{current_password:f.get('current_password')});
  });
 }
});
