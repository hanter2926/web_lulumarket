document.addEventListener('DOMContentLoaded', function(){
  const editBtn = document.getElementById('editProfileBtn');
  const modalEl = document.getElementById('editProfileModal');
  const saveBtn = document.getElementById('saveProfileBtn');
  const fullNameInput = document.getElementById('profileFullName');
  const phoneInput = document.getElementById('profilePhone');
  const deliveryInput = document.getElementById('profileDelivery');

  // bootstrap modal
  let bsModal = null;
  if (typeof bootstrap !== 'undefined' && modalEl) {
    bsModal = new bootstrap.Modal(modalEl);
  }

  // populate fields from page
  if (editBtn){
    editBtn.addEventListener('click', function(){
      // read values from page (use spans added to template)
      fullNameInput.value = document.getElementById('profileFullNameDisplay')?.textContent?.trim() || '';
      phoneInput.value = document.getElementById('profilePhoneDisplay')?.textContent?.trim() || '';
      deliveryInput.value = document.getElementById('profileDeliveryDisplay')?.textContent?.trim() || '';
      if (bsModal) bsModal.show();
    });
  }

  async function getCsrf(){
    const cookie = document.cookie.split(';').map(c=>c.trim()).find(c=>c.startsWith('csrftoken='));
    return cookie ? cookie.split('=')[1] : '';
  }

  if (saveBtn){
    saveBtn.addEventListener('click', async function(){
      const payload = {
        full_name: fullNameInput.value,
        phone: phoneInput.value,
        delivery_location: deliveryInput.value
      };
      const csrftoken = await getCsrf();
      try{
        const res = await fetch('/accounts/profiles/update_profile/', {
          method: 'PATCH',
          credentials: 'same-origin',
          headers: {
            'Content-Type':'application/json',
            'X-CSRFToken': csrftoken,
            'Accept':'application/json'
          },
          body: JSON.stringify(payload)
        });
        if (res.ok){
          const data = await res.json();
          // update DOM values without full reload
          document.getElementById('profileFullNameDisplay').textContent = data.full_name || 'Not added yet';
          document.getElementById('profilePhoneDisplay').textContent = data.phone || 'Not added yet';
          document.getElementById('profileDeliveryDisplay').textContent = data.delivery_location || 'Not added yet';
          if (bsModal) bsModal.hide();
        } else {
          const txt = await res.text();
          alert('Failed to update profile');
          console.error('Profile update failed:', res.status, txt);
        }
      }catch(err){
        console.error(err);
        alert('Error updating profile');
      }
    });
  }
});
