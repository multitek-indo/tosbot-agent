document.getElementById('login-form').addEventListener('submit',async e=>{
 e.preventDefault();const form=e.currentTarget,btn=form.querySelector('button'),err=document.getElementById('err');err.textContent='';btn.disabled=true;
 try { const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify({username:document.getElementById('username').value,password:document.getElementById('password').value})});const data=await res.json();if(!res.ok)throw Error(data.detail||'Gagal masuk'); location.href='/'; }catch(ex){err.textContent=ex.message;}finally{btn.disabled=false;}
});

// Nama/logo perusahaan bersifat publik agar terlihat sebelum login.
(async()=>{try{const r=await fetch('/api/branding',{cache:'no-store'});if(!r.ok)return;const b=await r.json();
 document.querySelectorAll('.company-name').forEach(el=>{el.textContent=b.company_name});
 document.title='Masuk — '+b.company_name;
 const logo=document.querySelector('.brand-logo .brand-img'),fallback=document.querySelector('.brand-fallback');
 if(b.has_logo){logo.src=b.logo_url+'?v='+Date.now();logo.hidden=false;fallback.hidden=true}
 else{fallback.textContent=(b.company_name||'M').charAt(0).toUpperCase()}
 }catch(e){console.warn('Branding belum termuat')}})();
