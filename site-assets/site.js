'use strict';
const menuButton = document.querySelector('.menu-toggle');
const navigation = document.getElementById('navigation');
function closeMenu() {
  menuButton.setAttribute('aria-expanded', 'false');
  navigation.classList.remove('is-open');
}
menuButton.addEventListener('click', () => {
  const open = menuButton.getAttribute('aria-expanded') !== 'true';
  menuButton.setAttribute('aria-expanded', String(open));
  navigation.classList.toggle('is-open', open);
});
navigation.querySelectorAll('a').forEach(link => link.addEventListener('click', closeMenu));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && menuButton.getAttribute('aria-expanded') === 'true') {
    closeMenu(); menuButton.focus();
  }
});
const tabs = [...document.querySelectorAll('[data-tab]')];
const tablist = document.querySelector('[role="tablist"]');
const mobile = matchMedia('(max-width: 600px)');
function updateOrientation() {
  tablist.setAttribute('aria-orientation', mobile.matches ? 'horizontal' : 'vertical');
  closeMenu();
}
mobile.addEventListener('change', updateOrientation);
updateOrientation();
function selectTab(button, focus = false) {
  tabs.forEach(tab => {
    const selected = tab === button;
    tab.setAttribute('aria-selected', String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute('aria-controls')).hidden = !selected;
  });
  if (focus) button.focus();
}
tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(tab));
  tab.addEventListener('keydown', event => {
    let next;
    const forward = mobile.matches ? 'ArrowRight' : 'ArrowDown';
    const backward = mobile.matches ? 'ArrowLeft' : 'ArrowUp';
    if (event.key === forward) next = (index + 1) % tabs.length;
    else if (event.key === backward) next = (index + tabs.length - 1) % tabs.length;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = tabs.length - 1;
    else return;
    event.preventDefault(); selectTab(tabs[next], true);
  });
});
const paperButtons = [...document.querySelectorAll('.save-paper')];
paperButtons.forEach(button => button.addEventListener('click', () => {
  const selected = button.getAttribute('aria-pressed') !== 'true';
  button.setAttribute('aria-pressed', String(selected));
  button.textContent = selected ? '✓' : '＋';
  const count = paperButtons.filter(item => item.getAttribute('aria-pressed') === 'true').length;
  document.getElementById('selection-status').textContent = count ? `已标记 ${count} 篇待读 · 仅本页演示` : '点击 ＋，体验标记待读';
}));
document.getElementById('copy-command').addEventListener('click', async () => {
  const status = document.getElementById('copy-status');
  try {
    await navigator.clipboard.writeText(document.getElementById('clone-command').textContent);
    status.textContent = '已复制克隆命令';
  } catch {
    status.textContent = '自动复制不可用，请选中命令手动复制。';
  }
});
