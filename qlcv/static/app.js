document.addEventListener('submit', (event) => {
  const message = event.target.dataset.confirm;
  if (message && !window.confirm(message)) event.preventDefault();
});
const slider = document.getElementById('progress');
if (slider) slider.addEventListener('input', () => {
  document.getElementById('progress-output').value = `${Number(slider.value)}%`;
});
