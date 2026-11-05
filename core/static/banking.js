(() => {
  const status = document.querySelector('#bank-status');
  let busy = false;
  const say = text => { status.textContent = text; };
  const bankOrigin = status?.dataset.bankOrigin;
  function correctAddress() {
    if (!bankOrigin || window.location.origin === bankOrigin) return true;
    say('Bank connections use your configured HTTPS address. ');
    const link = document.createElement('a');
    link.href = bankOrigin + '/expenses/';
    link.textContent = 'Open secure Money →';
    status.append(link);
    return false;
  }
  async function post(path, body = {}) {
    const response = await fetch('/expenses/bank/' + path, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json', 'X-LifeHub': '1'},
      body: JSON.stringify(body),
    });
    let result;
    try { result = await response.json(); }
    catch {
      if (response.status === 401) throw new Error('Your LifeHub sign-in is required. Reload this page and sign in again.');
      if (response.status === 403) throw new Error('This request was blocked. Open Money at your configured HTTPS address and try again.');
      throw new Error('The server could not complete this action. Reload Money to check its status.');
    }
    if (!response.ok) throw new Error(result.error || (typeof result.detail === 'string' ? result.detail : 'The bank action failed.'));
    return result;
  }
  let scriptPromise;
  function loadPlaid() {
    if (window.Plaid) return Promise.resolve();
    if (!scriptPromise) scriptPromise = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = 'https://cdn.plaid.com/link/v2/stable/link-initialize.js';
      script.onload = resolve;
      script.onerror = () => { scriptPromise = null; reject(new Error('Could not load the bank connection window. Please try again.')); };
      document.head.append(script);
    });
    return scriptPromise;
  }
  async function connect(itemId = null, resume = false) {
    if (!correctAddress()) return;
    if (busy) return;
    busy = true;
    say('Opening secure bank connection…');
    try {
      await loadPlaid();
      const result = await post(resume ? 'resume' : 'link', resume ? {} : {item_id: itemId});
      const options = {
        token: result.link_token,
        onSuccess: async publicToken => {
          say('Saving your connection and starting the first import…');
          try {
            await post('complete', {public_token: publicToken || null});
            window.location.assign('/expenses/');
          } catch (error) {
            say(error.message + ' Reload Money to check whether the connection was saved before retrying.');
            busy = false;
          }
        },
        onExit: error => {
          say(error ? 'The bank connection was not completed. Return to Money and try again.' : 'Bank connection window closed.');
          busy = false;
        },
      };
      if (resume) options.receivedRedirectUri = window.location.href;
      window.Plaid.create(options).open();
    } catch (error) { say(error.message); busy = false; }
  }
  document.querySelector('#connect-bank')?.addEventListener('click', () => connect());
  document.querySelectorAll('[data-reconnect]').forEach(button => button.addEventListener('click', () => connect(button.dataset.reconnect)));
  async function action(path, body, message) {
    if (!correctAddress()) return;
    if (busy) return;
    busy = true;
    say(message);
    try { await post(path, body); window.location.reload(); }
    catch (error) { say(error.message); busy = false; }
  }
  document.querySelector('#sync-bank')?.addEventListener('click', () => action('sync', {}, 'Importing available bank updates…'));
  document.querySelectorAll('[data-disconnect]').forEach(button => button.addEventListener('click', () => {
    if (confirm('Disconnect this bank and remove its imported transactions from LifeHub? Manual entries are kept.'))
      action('disconnect', {item_id: button.dataset.disconnect}, 'Disconnecting bank…');
  }));
  if (!correctAddress()) {
    document.querySelectorAll('#connect-bank, #sync-bank, [data-reconnect], [data-disconnect]').forEach(button => { button.disabled = true; });
  } else if (document.querySelector('#oauth-resume')) connect(null, true);
})();
