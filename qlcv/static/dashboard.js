const data = JSON.parse(document.getElementById('chart-data').textContent);
Chart.defaults.font.family = 'Segoe UI, Arial, sans-serif';
Chart.defaults.color = '#64748b';
const projects = document.getElementById('project-chart');
if (projects) new Chart(projects, {
  type: 'bar',
  data: { labels: data.names, datasets: [{ label: 'Tiến độ (%)', data: data.progress, backgroundColor: '#168b86', borderRadius: 5, maxBarThickness: 56 }] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { min: 0, max: 100, ticks: { callback: value => `${value}%` }, grid: { color: '#edf1f5' } }, x: { grid: { display: false } } } }
});
const tasks = document.getElementById('task-chart');
if (tasks) new Chart(tasks, {
  type: 'pie',
  data: { labels: ['Chưa làm', 'Đang làm', 'Hoàn thành'], datasets: [{ data: data.counts, backgroundColor: ['#cbd5e1', '#eeb24a', '#168b86'], borderWidth: 3, borderColor: '#fff' }] },
  options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom', labels: { padding: 18, usePointStyle: true } }, tooltip: { callbacks: { label: context => `${context.label}: ${context.raw} (${(100 * context.raw / data.counts.reduce((a, b) => a + b, 0)).toFixed(1)}%)` } } } }
});
