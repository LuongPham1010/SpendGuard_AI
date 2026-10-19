/* SpendGuard assistant console. Plain JS, no build step.
   The answer is shown in plain language first; the agent's pipeline, tiers and verdicts sit in a
   collapsible "How SpendGuard decided" panel under each answer. Labels follow the EN / VI switch. */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const esc = (s) => (s == null ? '' : String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])));
  const vnd = (n) => (n == null || isNaN(n) ? '0 VND' : Number(n).toLocaleString('en-US') + ' VND');

  const PHASES = ['INTAKE', 'GUARDRAIL', 'PLAN', 'PREFLIGHT', 'EXECUTE', 'REPLAN', 'AWAIT_HUMAN', 'REFLECT', 'RESPOND'];

  /* ---------- labels (EN / VI) ---------- */
  const TEXT = {
    en: {
      thinking: {
        INTAKE: 'Reading your profile and statement…',
        GUARDRAIL: 'Checking for hidden instructions and masking personal data…',
        PLAN: 'Choosing what to do…',
        PREFLIGHT: 'Checking limits and scam risk…',
        EXECUTE: 'Doing the steps I am allowed to do…',
        REPLAN: 'Looking for useful follow-ups…',
        AWAIT_HUMAN: 'Preparing anything that needs your approval…',
        REFLECT: 'Checking every number against your data…'
      },
      phase: { INTAKE: 'Intake', GUARDRAIL: 'Guardrail', PLAN: 'Plan', PREFLIGHT: 'Preflight', EXECUTE: 'Execute',
               REPLAN: 'Replan', AWAIT_HUMAN: 'Your approval', REFLECT: 'Verify', RESPOND: 'Answer' },
      tool: {
        get_transactions: 'Read transactions', get_budget_status: 'Budget check', categorize_transactions: 'Categorise spending',
        scan_subscriptions: 'Find subscriptions', cancel_subscription: 'Cancel subscription', run_stress_test: 'Stress test',
        get_wallets: 'Wallet balances', transfer_internal: 'Move between your wallets', transfer_external: 'Send to another account',
        guardian_scan: 'Scam check', second_opinion: 'Second opinion', read_receipt: 'Read receipt',
        read_chat_screenshot: 'Read chat screenshot', run_my_month_report: 'Month report', check_payee: 'Check the payee',
        set_budget: 'Set a budget cap', explain_transaction: 'Explain a charge', remember: 'Remember', recall: 'Recall',
        scan_past_transactions: 'Check past payments for scams'
      },
      verdict: { EXECUTE: 'Done automatically', AWAIT_HUMAN: 'Waiting for your approval', LOCKED: 'Frozen by Guardian', REJECT: 'Not done' },
      tier: { 'Tier 1': 'Tier 1 · read-only', 'Tier 2': 'Tier 2 · auto', 'Tier 3': 'Tier 3 · needs you' },
      intent: {
        run_my_month: 'Month review', budget_status: 'Budget', subscriptions: 'Subscriptions', cancel_subscription: 'Subscriptions',
        stress_test: 'Stress test', second_opinion: 'Second opinion', wallets: 'Wallets', transfer_internal: 'Wallet transfer',
        transfer_external: 'Outgoing transfer', set_budget: 'Budget cap', explain_transaction: 'Explain a charge',
        read_receipt: 'Receipt', remember: 'Memory', recall: 'Memory', scan_past_transactions: 'Scam check',
        scam_check: 'Screenshot check'
      },
      evidence: {
        authority_impersonation: 'The message claims to be from the police, a prosecutor or a court',
        urgency: 'It pressures you to act right now',
        secrecy: 'It asks you to keep this secret',
        safe_account: "It asks you to move money into a 'safe' or 'holding' account",
        task_scheme: "It pays commission for online 'tasks' and then asks you to deposit money",
        prize: 'It says you won a prize but must pay first',
        otp_request: 'It asks for an OTP or a password',
        romance: 'Someone you met online is asking for money',
        customs_fee: 'It asks you to pay a parcel or customs fee',
        refund_scam: 'It promises a refund that needs a payment first',
        relative_emergency: 'A "relative" suddenly needs money urgently',
        fake_receipt: 'It shows a transfer receipt that may be fake',
        new_payee: 'You have never paid this account before'
      },
      scam: {
        authority_impersonation: 'Fake police or official', investment_ponzi: 'Too-good-to-be-true investment',
        task_scheme: 'Online task scam', otp_request: 'OTP theft', prize: 'Fake prize', romance: 'Romance scam',
        customs_fee: 'Fake customs fee', refund_scam: 'Fake refund', relative_emergency: 'Fake relative emergency',
        fake_receipt: 'Fake receipt', reported_account: 'Reported scam account', safe_account: "Fake 'safe account'"
      },
      reasons: {
        'high-risk action requires human approval': 'Above your automatic limit, so it needs you',
        'guardian lockdown': 'Guardian froze it as a likely scam',
        'Tier 2 daily cap exceeded': "Today's automatic limit is used up",
        "injection suspected in this turn's inputs": 'Suspicious instructions were found in your data'
      },
      you: 'You', agent: 'SpendGuard', howDecided: 'How SpendGuard decided', steps: 'steps', grounded: 'every number checked',
      regenerated: 'answer rewritten from verified numbers', toolsRun: 'actions run', queued: 'waiting for you',
      needsApproval: 'Needs your approval', frozen: 'Frozen by Guardian', approve: 'Approve', unlock: 'Unlock with safety quiz',
      reject: 'Cancel', move: 'Move', send: 'Send', to: 'To', bank: 'Bank', account: 'Account', cancelSub: 'Cancel',
      quickCancel: 'Cancel a subscription:', perMonth: '/month', injection: '⚠ Suspicious instructions were found in your data, so every action in this turn waits for your approval.',
      coolingLeft: (m, s) => `Cooling-off ${m}:${s} left · then a short safety quiz`, coolingDone: '✓ Cooling-off over · you can take the safety quiz',
      nothingWaiting: 'Nothing is waiting. Read-only work and small moves between your wallets run on their own.',
      total: 'Total balance', done: 'Done: approved and carried out.', cancelled: 'Cancelled.', stillWaiting: 'Still waiting:',
      requestFailed: 'Something went wrong:', running: 'Working…', send_btn: 'Send', attach: 'Attach screenshot',
      quizTitle: 'Quick safety check', quizIntro: 'Answer these 3 questions to unlock the transfer. They are here to break the pressure scammers create.',
      quizSubmit: 'Check answers and unlock', quizCancel: 'Not now', waitCooling: (s) => `Please wait ${s}s. The pause is part of the protection. You can cancel the transfer at any time.`,
      frozenTitle: 'Transfer frozen', frozenLede: 'Your money has not moved. This looks like a known scam pattern.',
      sawH: 'Why I stopped it', knowH: 'What you should know', review: 'Review in the approval list',
      coolingShort: (s) => `Cooling-off: ${s}s`, coolingOver: '✓ Cooling-off over · safety quiz available', behaviourOnly: 'Unusual for your account (new payee, size or timing)',
      scamRisk: 'Scam risk',
      otpTitle: 'Confirm with your one-time code', otpIntro: 'Approvals need the 6-digit code sent to your phone.',
      otpConfirm: 'Confirm and approve', otpWrong: 'That code did not work:', notifTitle: 'Notifications', notifEmpty: 'No notifications yet.',
      push: '📲 [simulated push]',
      micStart: 'Speak your request', micStop: 'Stop listening', micListening: 'Listening… press ■ when you are done',
      micCheck: 'Check the text, then press Send.', micDenied: 'Microphone blocked. Allow it in the browser address bar.',
      micNoSpeech: 'No speech heard. Try again.', micError: 'Voice input stopped:',
      readAloud: 'Read aloud', stopReading: 'Stop reading'
    },
    vi: {
      thinking: {
        INTAKE: 'Đang đọc hồ sơ và sao kê…',
        GUARDRAIL: 'Đang kiểm tra chỉ thị ẩn và che dữ liệu cá nhân…',
        PLAN: 'Đang chọn việc cần làm…',
        PREFLIGHT: 'Đang kiểm tra hạn mức và rủi ro lừa đảo…',
        EXECUTE: 'Đang thực hiện các bước được phép…',
        REPLAN: 'Đang tìm bước tiếp theo hữu ích…',
        AWAIT_HUMAN: 'Đang chuẩn bị các việc cần bạn duyệt…',
        REFLECT: 'Đang đối chiếu mọi con số với dữ liệu…'
      },
      phase: { INTAKE: 'Tiếp nhận', GUARDRAIL: 'Rào chắn', PLAN: 'Lập kế hoạch', PREFLIGHT: 'Kiểm tra trước', EXECUTE: 'Thực hiện',
               REPLAN: 'Bổ sung', AWAIT_HUMAN: 'Chờ duyệt', REFLECT: 'Đối chiếu', RESPOND: 'Trả lời' },
      tool: {
        get_transactions: 'Đọc giao dịch', get_budget_status: 'Kiểm tra ngân sách', categorize_transactions: 'Phân loại chi tiêu',
        scan_subscriptions: 'Tìm gói đăng ký', cancel_subscription: 'Hủy gói đăng ký', run_stress_test: 'Kiểm tra sức chịu đựng',
        get_wallets: 'Số dư ví', transfer_internal: 'Chuyển giữa các ví', transfer_external: 'Chuyển sang tài khoản khác',
        guardian_scan: 'Kiểm tra lừa đảo', second_opinion: 'Ý kiến thứ hai', read_receipt: 'Đọc hóa đơn',
        read_chat_screenshot: 'Đọc ảnh chụp tin nhắn', run_my_month_report: 'Báo cáo tháng', check_payee: 'Kiểm tra người nhận',
        set_budget: 'Đặt hạn mức', explain_transaction: 'Giải thích khoản phí', remember: 'Ghi nhớ', recall: 'Nhắc lại',
        scan_past_transactions: 'Rà soát khoản đã chi'
      },
      verdict: { EXECUTE: 'Đã tự động thực hiện', AWAIT_HUMAN: 'Chờ bạn duyệt', LOCKED: 'Guardian đã khóa', REJECT: 'Không thực hiện' },
      tier: { 'Tier 1': 'Tier 1 · chỉ đọc', 'Tier 2': 'Tier 2 · tự động', 'Tier 3': 'Tier 3 · cần bạn' },
      intent: {
        run_my_month: 'Rà soát tháng', budget_status: 'Ngân sách', subscriptions: 'Gói đăng ký', cancel_subscription: 'Gói đăng ký',
        stress_test: 'Sức chịu đựng', second_opinion: 'Ý kiến thứ hai', wallets: 'Ví', transfer_internal: 'Chuyển giữa ví',
        transfer_external: 'Chuyển ra ngoài', set_budget: 'Hạn mức', explain_transaction: 'Giải thích khoản phí',
        read_receipt: 'Hóa đơn', remember: 'Ghi nhớ', recall: 'Ghi nhớ', scan_past_transactions: 'Kiểm tra lừa đảo',
        scam_check: 'Kiểm tra ảnh tin nhắn'
      },
      evidence: {
        authority_impersonation: 'Tin nhắn tự xưng là công an, viện kiểm sát hoặc tòa án',
        urgency: 'Thúc ép bạn phải làm ngay',
        secrecy: 'Yêu cầu bạn giữ bí mật',
        safe_account: "Yêu cầu chuyển tiền vào 'tài khoản an toàn' hoặc 'tạm giữ'",
        task_scheme: "Trả hoa hồng cho 'nhiệm vụ' online rồi yêu cầu nạp tiền",
        prize: 'Báo bạn trúng thưởng nhưng phải nộp tiền trước',
        otp_request: 'Hỏi mã OTP hoặc mật khẩu',
        romance: 'Người quen qua mạng hỏi vay tiền',
        customs_fee: 'Yêu cầu nộp phí hải quan / bưu kiện',
        refund_scam: 'Hứa hoàn tiền nhưng phải chuyển trước',
        relative_emergency: '"Người thân" bỗng cần tiền gấp',
        fake_receipt: 'Gửi biên lai chuyển khoản có thể là giả',
        new_payee: 'Bạn chưa từng chuyển tiền cho tài khoản này'
      },
      scam: {
        authority_impersonation: 'Giả danh công an / cơ quan nhà nước', investment_ponzi: 'Đầu tư lãi cao bất thường',
        task_scheme: 'Lừa đảo làm nhiệm vụ online', otp_request: 'Đánh cắp OTP', prize: 'Trúng thưởng giả', romance: 'Lừa tình cảm',
        customs_fee: 'Phí hải quan giả', refund_scam: 'Hoàn tiền giả', relative_emergency: 'Người thân gặp nạn giả',
        fake_receipt: 'Biên lai giả', reported_account: 'Tài khoản đã bị tố cáo', safe_account: "'Tài khoản an toàn' giả"
      },
      reasons: {
        'high-risk action requires human approval': 'Vượt hạn mức tự động nên cần bạn duyệt',
        'guardian lockdown': 'Guardian khóa vì nghi lừa đảo',
        'Tier 2 daily cap exceeded': 'Đã dùng hết hạn mức tự động hôm nay',
        "injection suspected in this turn's inputs": 'Phát hiện chỉ thị đáng ngờ trong dữ liệu'
      },
      you: 'Bạn', agent: 'SpendGuard', howDecided: 'SpendGuard đã quyết định thế nào', steps: 'bước', grounded: 'đã đối chiếu mọi con số',
      regenerated: 'câu trả lời được viết lại từ số liệu đã kiểm', toolsRun: 'hành động đã chạy', queued: 'chờ bạn',
      needsApproval: 'Cần bạn duyệt', frozen: 'Guardian đã khóa', approve: 'Duyệt', unlock: 'Mở khóa bằng câu hỏi an toàn',
      reject: 'Hủy', move: 'Chuyển', send: 'Gửi', to: 'Tới', bank: 'Ngân hàng', account: 'STK', cancelSub: 'Hủy',
      quickCancel: 'Hủy một gói đăng ký:', perMonth: '/tháng', injection: '⚠ Phát hiện chỉ thị đáng ngờ trong dữ liệu, nên mọi hành động trong lượt này đều chờ bạn duyệt.',
      coolingLeft: (m, s) => `Còn ${m}:${s} chờ bình tĩnh · sau đó trả lời câu hỏi an toàn`, coolingDone: '✓ Hết thời gian chờ · có thể làm câu hỏi an toàn',
      nothingWaiting: 'Không có gì chờ duyệt. Việc chỉ đọc và chuyển nhỏ giữa các ví được tự động thực hiện.',
      total: 'Tổng số dư', done: 'Xong: đã duyệt và thực hiện.', cancelled: 'Đã hủy.', stillWaiting: 'Vẫn đang chờ:',
      requestFailed: 'Có lỗi xảy ra:', running: 'Đang xử lý…', send_btn: 'Gửi', attach: 'Đính kèm ảnh',
      quizTitle: 'Kiểm tra an toàn nhanh', quizIntro: 'Trả lời 3 câu hỏi để mở khóa lệnh chuyển. Các câu hỏi giúp bạn thoát khỏi áp lực mà kẻ lừa đảo tạo ra.',
      quizSubmit: 'Kiểm tra và mở khóa', quizCancel: 'Để sau', waitCooling: (s) => `Vui lòng chờ ${s} giây. Khoảng dừng này là một phần của lớp bảo vệ. Bạn có thể hủy lệnh bất cứ lúc nào.`,
      frozenTitle: 'Đã khóa lệnh chuyển', frozenLede: 'Tiền của bạn chưa bị chuyển đi. Đây giống một kịch bản lừa đảo đã biết.',
      sawH: 'Vì sao tôi chặn lại', knowH: 'Bạn nên biết', review: 'Xem trong danh sách chờ duyệt',
      coolingShort: (s) => `Thời gian chờ: ${s} giây`, coolingOver: '✓ Hết thời gian chờ · có thể làm câu hỏi an toàn', behaviourOnly: 'Bất thường so với thói quen (người nhận mới, số tiền hoặc thời điểm)',
      scamRisk: 'Rủi ro lừa đảo',
      otpTitle: 'Xác nhận bằng mã OTP', otpIntro: 'Mọi lệnh duyệt cần mã 6 số gửi tới điện thoại của bạn.',
      otpConfirm: 'Xác nhận và duyệt', otpWrong: 'Mã chưa đúng:', notifTitle: 'Thông báo', notifEmpty: 'Chưa có thông báo.',
      push: '📲 [thông báo mô phỏng]',
      micStart: 'Nói yêu cầu của bạn', micStop: 'Dừng nghe', micListening: 'Đang nghe… nói xong bấm ■ để dừng',
      micCheck: 'Kiểm tra lại chữ rồi bấm Gửi.', micDenied: 'Micro bị chặn. Hãy cho phép trên thanh địa chỉ trình duyệt.',
      micNoSpeech: 'Không nghe thấy gì. Thử lại nhé.', micError: 'Nhập giọng nói dừng:',
      readAloud: 'Đọc to', stopReading: 'Dừng đọc'
    }
  };
  const T = () => TEXT[window.SG_LANG === 'vi' ? 'vi' : 'en'];

  const sessionId = 'web-' + Math.random().toString(36).slice(2, 8);
  let attachment = null;
  let countdownTimers = [];
  let thinkingTimer = null;

  async function getJSON(url, opts = {}) {
    const res = await fetch(url, opts);
    if (res.status === 401) {
      toast('Access token missing. Open the link with ?token=...');
      throw new Error('401');
    }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return res.json();
  }

  function toast(msg) {
    const t = $('toast');
    if (!t) return;
    t.textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 3500);
  }

  function addNote(html) {
    $('conversation').insertAdjacentHTML('beforeend', `<div class="msg agent"><div class="note-banner">${html}</div></div>`);
    scrollConv();
  }

  function tierClass(tier) {
    if (tier === 'Tier 1') return 't1';
    if (tier === 'Tier 2') return 't2';
    return 't3';
  }

  function maskAccount(acc) {
    const s = String(acc || '').trim();
    if (!s) return '';
    return s.length >= 8 ? `${s.slice(0, 3)}****${s.slice(-3)}` : '****';
  }

  const toolLabel = (tool) => T().tool[tool] || String(tool || '').replace(/_/g, ' ');

  /* friendly title + detail line for a queued action */
  function describeAction(args, tool) {
    const L = T();
    args = args || {};
    const amt = args.amount ? vnd(args.amount) : '';
    if (tool === 'transfer_internal') {
      return { title: `${L.move} ${amt}`, detail: `<b>${esc(args.source || 'Main Wallet')}</b> → <b>${esc(args.destination || 'Emergency Vault')}</b>` };
    }
    if (tool === 'transfer_external') {
      const parts = [];
      if (args.payee_name) parts.push(`${L.to} <b>${esc(args.payee_name)}</b>`);
      if (args.bank) parts.push(`${L.bank} <b>${esc(String(args.bank).toUpperCase())}</b>`);
      if (args.payee_account) parts.push(`${L.account} <b>${esc(maskAccount(args.payee_account))}</b>`);
      return { title: `${L.send} ${amt}`, detail: parts.join(' · ') };
    }
    if (tool === 'cancel_subscription') return { title: `${toolLabel(tool)}: ${esc(args.merchant || '')}`, detail: '' };
    if (tool === 'set_budget') return { title: `${toolLabel(tool)}: ${esc(args.category || '')} ${args.monthly_cap ? vnd(args.monthly_cap) : ''}`, detail: '' };
    return { title: esc(`${toolLabel(tool)} ${amt}`.trim()), detail: '' };
  }

  function friendlyReasons(reasons) {
    const L = T();
    return (reasons || [])
      .filter(r => !/^classified as|^dry-run ok$/.test(r))
      .map(r => {
        const m = /^guardian risk ([\d.]+)/.exec(r);
        if (m) return `${L.scamRisk} ${Math.round(Number(m[1]))}/100`;
        return L.reasons[r] || r;
      });
  }

  /* backend wording -> reader wording (display only; the audited text is unchanged) */
  function humanize(text) {
    const L = T();
    return String(text || '')
      .replace(/Matched pattern '([a-z_]+)'/g, (m, k) => L.evidence[k] || k.replace(/_/g, ' '))
      .replace(/Payee account has never been paid before/g, L.evidence.new_payee)
      .replace(/pattern: ([a-z_]+)/g, (m, k) => L.scam[k] || k.replace(/_/g, ' '))
      .replace(/\b(transfer_internal|transfer_external|cancel_subscription|set_budget)\b/g, (m) => L.tool[m] || m)
      .replace(/ \(AWAIT_HUMAN\)/g, '')
      .replace(/\(LOCKED\)/g, `(${L.verdict.LOCKED.toLowerCase()})`)
      .replace(/: EXECUTED\./g, ': ✓')
      .replace(/FLAGGED_FOR_CANCELLATION/g, '✓');
  }

  /* response text -> paragraphs, bullet lists and a preformatted block for drafted notices */
  function formatResponse(text) {
    const lines = humanize(text).split('\n');
    let html = '';
    let inList = false;
    const closeList = () => { if (inList) { html += '</ul>'; inList = false; } };
    for (let i = 0; i < lines.length; i++) {
      const ln = lines[i];
      if (/^Draft cancellation notice/.test(ln)) {
        closeList();
        const rest = lines.slice(i + 1);
        const endIdx = rest.findIndex(l => /^Queued for your approval|^Not executed/.test(l));
        const body = endIdx === -1 ? rest : rest.slice(0, endIdx);
        html += `<p><b>${esc(ln)}</b></p><pre>${esc(body.join('\n').trim())}</pre>`;
        if (endIdx === -1) return html;
        i += endIdx;
        continue;
      }
      if (/^\s*-\s+/.test(ln)) {
        if (!inList) { html += '<ul>'; inList = true; }
        html += `<li>${esc(ln.replace(/^\s*-\s+/, ''))}</li>`;
        continue;
      }
      closeList();
      if (!ln.trim()) continue;
      html += `<p>${esc(ln)}</p>`;
    }
    closeList();
    return html;
  }

  /* ---------- theme ---------- */
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem('sg-theme', next); } catch (e) { /* storage blocked: theme still applies for this visit */ }
  }

  /* ---------- model chip & health ---------- */
  async function loadHealth() {
    try {
      const h = await getJSON('/api/health');
      const m = $('chip-model');
      if (m) {
        m.className = 'chip hide-sm ' + (h.gemini_configured ? 'on' : 'off');
        m.querySelector('span').textContent = h.gemini_configured ? `${h.gemini_model} · ${h.gemini_keys} key${h.gemini_keys === 1 ? '' : 's'}` : 'Offline mode (rules)';
      }
      const tx = $('chip-tx');
      if (tx) {
        tx.className = 'chip hide-sm ' + (h.loaded_transactions_count > 0 ? 'on' : 'off');
        tx.querySelector('span').textContent = `${h.loaded_transactions_count} transactions`;
      }
    } catch (e) { /* shown by toast */ }
  }

  /* ---------- pipeline rail & live thinking progress ---------- */
  function setNode(n, cls, detail) {
    n.className = cls;
    const d = n.querySelector('.detail');
    d.textContent = detail;
    n.title = detail;
  }

  function resetRail() {
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
    PHASES.forEach(p => {
      const n = document.querySelector(`.node[data-phase="${p}"]`);
      if (n) setNode(n, 'node', '');
    });
  }

  function startThinkingProgress() {
    resetRail();
    const L = T();
    let idx = 0;
    const bubbleId = 'thinking-' + Date.now();
    $('conversation').insertAdjacentHTML('beforeend', `
      <div class="msg agent thinking-msg" id="${bubbleId}">
        <div class="who"><span class="agent-avatar">S</span>${esc(L.agent)}</div>
        <div class="bubble thinking-bubble">
          <div class="thinking-header">
            <span class="spinner-dot"></span>
            <span class="thinking-title">${esc(L.thinking[PHASES[0]])}</span>
          </div>
          <div class="thinking-steps">
            ${PHASES.slice(0, 8).map((p, i) => `<span class="t-step ${i === 0 ? 'running' : ''}" data-tstep="${p}">${esc(L.phase[p])}</span>`).join('')}
          </div>
        </div>
      </div>`);
    scrollConv();

    const firstNode = document.querySelector(`.node[data-phase="${PHASES[0]}"]`);
    if (firstNode) setNode(firstNode, 'node active pulse', '…');

    thinkingTimer = setInterval(() => {
      idx = Math.min(idx + 1, 7);
      const curPhase = PHASES[idx];
      const n = document.querySelector(`.node[data-phase="${curPhase}"]`);
      if (n) setNode(n, 'node active pulse', '…');
      const box = $(bubbleId);
      if (box) {
        const titleEl = box.querySelector('.thinking-title');
        if (titleEl) titleEl.textContent = T().thinking[curPhase] || curPhase;
        box.querySelectorAll('.t-step').forEach((el, i) => {
          el.className = 't-step ' + (i < idx ? 'done' : (i === idx ? 'running' : ''));
        });
      }
    }, 320);

    return bubbleId;
  }

  function stopThinkingProgress(bubbleId) {
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
    const box = $(bubbleId);
    if (box) box.remove();
  }

  function playRail(turn) {
    resetRail();
    const present = (turn.trace || []).filter(t => PHASES.includes(t.phase));
    const verdicts = (turn.decisions || []).map(d => d.verdict);
    present.forEach((t, i) => {
      setTimeout(() => {
        const n = document.querySelector(`.node[data-phase="${t.phase}"]`);
        if (!n) return;
        let cls = 'node active pulse';
        if (t.phase === 'GUARDRAIL' && turn.flags.includes('INJECTION_SUSPECTED')) cls = 'node warn pulse';
        if (t.phase === 'PREFLIGHT' && verdicts.includes('LOCKED')) cls = 'node alarm pulse';
        if (t.phase === 'PREFLIGHT' && !verdicts.includes('LOCKED') && verdicts.includes('AWAIT_HUMAN')) cls = 'node warn pulse';
        if (t.phase === 'AWAIT_HUMAN') cls = verdicts.includes('LOCKED') ? 'node alarm pulse' : 'node warn pulse';
        if (t.phase === 'REFLECT' && turn.reflect && turn.reflect.regenerated) cls = 'node warn pulse';
        setNode(n, cls, railDetail(t, turn));
      }, 90 * i);
    });
  }

  function railDetail(t, turn) {
    switch (t.phase) {
      case 'INTAKE': return t.detail;
      case 'GUARDRAIL': return turn.flags.includes('INJECTION_SUSPECTED') ? 'injection suspected' : 'clean';
      case 'PLAN': return (turn.plan || []).map(c => toolLabel(c.tool)).join(' → ') || 'no tools';
      case 'PREFLIGHT': return (turn.decisions || []).map(d => `${toolLabel(d.call.tool)}: ${T().verdict[d.verdict] || d.verdict}`).join(' · ');
      case 'EXECUTE': return `${turn.results.length} ${T().toolsRun}`;
      case 'REPLAN': return t.detail.replace('added ', '+ ');
      case 'AWAIT_HUMAN': return `${turn.queued.length} ${T().queued}`;
      case 'REFLECT': return turn.reflect.grounded ? T().grounded : T().regenerated;
      default: return t.detail;
    }
  }

  /* ---------- chat stream ---------- */
  function scrollConv() {
    const c = $('conversation');
    if (c) c.scrollTop = c.scrollHeight;
  }

  /* ---------- voice: speech to text into the input box, and read-aloud ----------
     Uses the browser's Web Speech API (Chrome, Edge). Speech only fills the input: the user still
     reads it and presses Send, so a misheard sentence never reaches the agent on its own. */
  const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const canSpeak = 'speechSynthesis' in window;
  let recognizer = null;
  // Press 🎤 to start, press again to stop. The browser ends a session after a pause, so while the user
  // still wants to talk a new session starts and its words are appended; a hard cap stops a forgotten mic.
  const MIC_MAX_MS = 120000;
  const mic = { wanted: false, base: '', heard: '', session: '', timer: null };

  function micLabel(listening) {
    const mic = $('mic');
    if (!mic) return;
    mic.classList.toggle('listening', listening);
    mic.textContent = listening ? '■' : '🎤';
    mic.title = listening ? T().micStop : T().micStart;
    mic.setAttribute('aria-label', mic.title);
  }

  function toggleMic() {
    if (mic.wanted) { stopMic(); return; }
    const input = $('input');
    mic.wanted = true;
    mic.base = input.value ? input.value.trimEnd() + ' ' : '';
    mic.heard = '';
    mic.timer = setTimeout(stopMic, MIC_MAX_MS);
    micLabel(true);
    toast(T().micListening);
    startRecognizer();
  }

  function stopMic() {
    mic.wanted = false;
    clearTimeout(mic.timer);
    if (recognizer) recognizer.stop();   // its onend finishes up
    else finishMic();
  }

  function finishMic() {
    recognizer = null;
    micLabel(false);
    const input = $('input');
    if (input.value.trim() !== mic.base.trim()) { toast(T().micCheck); input.focus(); }
  }

  function startRecognizer() {
    const input = $('input');
    const r = new Recognition();
    recognizer = r;
    r.lang = $('mic-lang').value;
    r.interimResults = true;
    r.continuous = true;
    mic.session = '';
    r.onresult = (e) => {
      let final = '', interim = '';
      for (let i = 0; i < e.results.length; i++) {
        if (e.results[i].isFinal) final += e.results[i][0].transcript;
        else interim += e.results[i][0].transcript;
      }
      mic.session = final;
      input.value = (mic.base + mic.heard + final + interim).replace(/\s+/g, ' ').trimStart();
    };
    r.onerror = (e) => {
      if (['not-allowed', 'service-not-allowed', 'audio-capture'].includes(e.error)) {
        mic.wanted = false; clearTimeout(mic.timer); toast(T().micDenied);
      } else if (e.error === 'network') {
        mic.wanted = false; clearTimeout(mic.timer); toast(`${T().micError} ${e.error}`);
      } else if (e.error === 'no-speech' && !mic.heard && !mic.session) {
        toast(T().micNoSpeech);      // silence so far; keep listening while the button is on
      }
    };
    r.onend = () => {
      if (mic.session) mic.heard += mic.session.trim() + ' ';
      mic.session = '';
      if (mic.wanted) setTimeout(startRecognizer, 150);   // the browser paused: keep listening until the user presses stop
      else finishMic();
    };
    r.start();
  }

  function speechLang(text) {
    return /[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]/i.test(text) ? 'vi-VN' : 'en-US';
  }

  function speak(text, btn) {
    if (!canSpeak) return;
    const synth = window.speechSynthesis;
    const stopping = btn && btn.hasAttribute('data-speaking');      // a second click on the same button stops it
    synth.cancel();
    document.querySelectorAll('[data-speaking]').forEach(b => { b.removeAttribute('data-speaking'); b.title = T().readAloud; });
    if (stopping) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = speechLang(text);
    const voice = synth.getVoices().find(v => v.lang && v.lang.toLowerCase().startsWith(u.lang.slice(0, 2)));
    if (voice) u.voice = voice;
    if (btn) {
      btn.setAttribute('data-speaking', '');
      btn.title = T().stopReading;
      u.onend = () => { btn.removeAttribute('data-speaking'); btn.title = T().readAloud; };
    }
    synth.speak(u);
  }

  function speakButton() {
    return canSpeak ? `<button type="button" class="speak-btn" data-speak title="${esc(T().readAloud)}" aria-label="${esc(T().readAloud)}">🔊</button>` : '';
  }

  function addYou(text) {
    $('conversation').insertAdjacentHTML('beforeend',
      `<div class="msg you"><div class="who">${esc(T().you)}</div><div class="bubble plain">${esc(text)}</div></div>`);
    scrollConv();
  }

  function buildInlineActions(turn) {
    const L = T();
    const blocks = [];

    // Queued requests (AWAIT_HUMAN / LOCKED) with payee details, so nobody approves blind
    (turn.queued || []).forEach(q => {
      const locked = q.verdict === 'LOCKED';
      const until = (q.unlock && q.unlock.cooling_off_until) || '';
      const a = describeAction(q.args, q.tool);
      blocks.push(`
        <div class="inline-action-box ${locked ? 'is-locked' : 'is-await'}" data-req-box="${esc(q.id)}">
          <div class="ia-info">
            <span class="ia-badge">${locked ? '⛔ ' + esc(L.frozen) : '⏳ ' + esc(L.needsApproval)}</span>
            <span class="ia-title">${a.title}</span>
            ${a.detail ? `<span class="ia-details">${a.detail}</span>` : ''}
            ${locked ? `<span class="ia-cool cool" data-until="${esc(until)}"></span>` : ''}
          </div>
          <div class="ia-btns">
            <button type="button" class="ia-btn ${locked ? 'unlock' : 'approve'}" data-approve="${esc(q.id)}" data-quiz="${!!(q.unlock && q.unlock.quiz_required)}" data-until="${esc(until)}">
              ${locked ? '🔓 ' + esc(L.unlock) : '✓ ' + esc(L.approve)}
            </button>
            <button type="button" class="ia-btn reject" data-reject="${esc(q.id)}">✕ ${esc(L.reject)}</button>
          </div>
        </div>`);
    });

    // One-click cancel chips for detected subscriptions
    const subRes = (turn.results || []).find(r => r.tool === 'scan_subscriptions' && r.output && r.output.subscriptions);
    if (subRes) {
      const activeSubs = subRes.output.subscriptions.filter(s => s.status === 'active');
      if (activeSubs.length) {
        blocks.push(`
          <div class="inline-sub-actions">
            <span class="ia-sub-label">${esc(L.quickCancel)}</span>
            ${activeSubs.map(s => `
              <button type="button" class="ia-sub-chip" data-cancel-sub="${esc(s.merchant)}">
                ${esc(s.merchant)} · ${vnd(s.amount)}${esc(L.perMonth)}
              </button>`).join('')}
          </div>`);
      }
    }

    return blocks.length ? `<div class="inline-actions-wrap">${blocks.join('')}</div>` : '';
  }

  function addAgent(turn) {
    const L = T();
    const pills = (turn.trace || []).filter(t => PHASES.includes(t.phase)).map(t => {
      let st = '';
      if (t.phase === 'GUARDRAIL' && turn.flags.includes('INJECTION_SUSPECTED')) st = 'warn';
      if ((t.phase === 'PREFLIGHT' || t.phase === 'AWAIT_HUMAN') && turn.decisions.some(d => d.verdict === 'LOCKED')) st = 'alarm';
      else if ((t.phase === 'PREFLIGHT' || t.phase === 'AWAIT_HUMAN') && turn.decisions.some(d => d.verdict === 'AWAIT_HUMAN')) st = 'warn';
      return `<span class="step-pill ${st}" title="${esc(t.detail)}">${esc(L.phase[t.phase] || t.phase)}</span>`;
    });

    const cards = (turn.decisions || []).map(d => `
      <div class="card">
        <div class="row"><span class="tool">${esc(toolLabel(d.call.tool))}</span><span class="tier ${tierClass(d.tier)}">${esc(L.tier[d.tier] || d.tier)}</span></div>
        <div class="tool-id">${esc(d.call.tool)}</div>
        <div class="verdict ${esc(d.verdict)}">${esc(L.verdict[d.verdict] || d.verdict)}</div>
        <div class="reasons">${esc((d.reasons || []).join(' · '))}</div>
      </div>`).join('');

    const nResults = (turn.results || []).length;
    const nQueued = (turn.queued || []).length;
    const summary = [
      `${pills.length} ${L.steps}`,
      `${nResults} ${L.toolsRun}`,
      nQueued ? `${nQueued} ${L.queued}` : '',
      turn.reflect && turn.reflect.grounded ? `<span class="ok">✓ ${esc(L.grounded)}</span>` : `<span class="regen">↻ ${esc(L.regenerated)}</span>`
    ].filter(Boolean).join(' · ');

    const intent = L.intent[turn.intent];
    const injected = (turn.flags || []).includes('INJECTION_SUSPECTED');
    const hasWhy = pills.length || cards;

    $('conversation').insertAdjacentHTML('beforeend', `
      <div class="msg agent">
        <div class="who"><span class="agent-avatar">S</span>${esc(L.agent)}${intent ? `<span class="intent-tag">${esc(intent)}</span>` : ''}${speakButton()}</div>
        ${injected ? `<div class="injection-banner">${esc(L.injection)}</div>` : ''}
        <div class="bubble">${formatResponse(turn.response)}</div>
        ${buildInlineActions(turn)}
        ${hasWhy ? `
        <details class="why-details">
          <summary><b>${esc(L.howDecided)}</b><span class="meta">${summary}</span></summary>
          <div class="why-body">
            <div class="turn-stepper">${pills.join('<span class="step-arrow">→</span>')}</div>
            ${cards ? `<div class="cards">${cards}</div>` : ''}
          </div>
        </details>` : ''}
      </div>`);
    bindCoolingTimers();
    scrollConv();
  }

  async function send(text) {
    if (!text || !text.trim()) return;
    addYou(text);
    const fd = new FormData();
    fd.append('text', text);
    fd.append('session_id', sessionId);
    if (attachment) {
      fd.append('files', attachment, attachment.name);
      attachment = null;
      if ($('attach')) $('attach').textContent = T().attach;
    }
    const sendBtn = $('send');
    if (sendBtn) {
      sendBtn.disabled = true;
      sendBtn.textContent = T().running;
    }
    const thinkingId = startThinkingProgress();
    try {
      const turn = await getJSON('/api/agent/chat', { method: 'POST', body: fd });
      stopThinkingProgress(thinkingId);
      playRail(turn);
      addAgent(turn);
      const locked = (turn.decisions || []).find(d => d.verdict === 'LOCKED' && d.guardian);
      if (locked) showIntercept(locked.guardian, turn.queued && turn.queued[0] ? turn.queued[0].id : null);
      refreshSide();
    } catch (e) {
      stopThinkingProgress(thinkingId);
      addNote(`<span class="flag">${esc(T().requestFailed)} ${esc(e.message)}</span>`);
    } finally {
      if (sendBtn) {
        sendBtn.disabled = false;
        sendBtn.textContent = T().send_btn;
      }
    }
  }

  /* ---------- cooling-off timer loop ---------- */
  function bindCoolingTimers() {
    countdownTimers.forEach(clearInterval);
    countdownTimers = [];
    document.querySelectorAll('.cool[data-until]').forEach(el => {
      const until = el.dataset.until ? new Date(el.dataset.until).getTime() : 0;
      const tick = () => {
        const s = Math.max(0, Math.round((until - Date.now()) / 1000));
        el.textContent = s > 0
          ? T().coolingLeft(String(Math.floor(s / 60)).padStart(2, '0'), String(s % 60).padStart(2, '0'))
          : T().coolingDone;
        el.style.color = s > 0 ? 'var(--warn)' : 'var(--signal)';
      };
      tick();
      countdownTimers.push(setInterval(tick, 1000));
    });
  }

  /* ---------- right-hand deck (wallets, approvals, activity) ---------- */
  async function loadVaults() {
    try {
      const d = await getJSON('/api/dashboard/overview');
      const total = d.total_balance || (d.wallets || []).reduce((s, w) => s + w.balance, 0) || 1;
      const box = $('vaults');
      if (!box) return;
      box.classList.remove('empty');
      box.innerHTML = `<div class="wallet-total"><span>${esc(T().total)}</span><b>${vnd(d.total_balance)}</b></div>` +
        (d.wallets || []).map(w => {
          const pct = Math.round((w.balance / total) * 100);
          return `
          <div class="vault vault-${esc(w.id)}">
            <div class="row">
              <span>${esc(w.name)} <small>${pct}%</small></span>
              <span class="amt">${vnd(w.balance)}</span>
            </div>
            <div class="bar"><i style="width:${Math.max(3, pct)}%"></i></div>
          </div>`;
        }).join('');
    } catch (e) { /* ignore */ }
  }

  async function loadApprovals() {
    const L = T();
    try {
      const d = await getJSON('/api/agent/approvals');
      const box = $('approvals');
      const card = document.querySelector('.card-approvals');
      const badge = $('approval-count');
      if (!box) return;
      const pending = d.pending || [];
      if (badge) { badge.hidden = !pending.length; badge.textContent = pending.length; }
      if (card) {
        card.classList.toggle('has-pending', pending.length > 0);
        card.classList.toggle('has-locked', pending.some(p => p.verdict === 'LOCKED'));
      }
      if (!pending.length) {
        box.classList.add('empty');
        box.innerHTML = esc(L.nothingWaiting);
        bindCoolingTimers();
        return;
      }
      box.classList.remove('empty');
      box.innerHTML = pending.map(p => {
        const locked = p.verdict === 'LOCKED';
        const until = (p.unlock && p.unlock.cooling_off_until) || '';
        const a = describeAction(p.args, p.tool);
        const why = friendlyReasons(p.reasons).slice(0, 2).join(' · ');
        return `<div class="req ${locked ? 'locked' : ''}" data-id="${esc(p.id)}">
          <div class="top"><span class="tool">${locked ? '⛔ ' + esc(L.frozen) : esc(L.needsApproval)}</span><span class="tier ${tierClass(p.tier)}">${esc(L.tier[p.tier] || p.tier)}</span></div>
          <div class="amt">${a.title}</div>
          ${a.detail ? `<div class="details">${a.detail}</div>` : ''}
          ${why ? `<div class="why">${esc(why)}</div>` : ''}
          ${locked ? `<div class="cool" data-until="${esc(until)}"></div>` : ''}
          <div class="acts">
            <button type="button" class="${locked ? 'unlock' : 'approve'}" data-approve="${esc(p.id)}" data-quiz="${!!(p.unlock && p.unlock.quiz_required)}" data-until="${esc(until)}">${locked ? '🔓 ' + esc(L.unlock) : '✓ ' + esc(L.approve)}</button>
            <button type="button" class="reject-btn" data-reject="${esc(p.id)}">✕ ${esc(L.reject)}</button>
          </div></div>`;
      }).join('');
      bindCoolingTimers();
    } catch (e) { /* ignore */ }
  }

  async function loadAudit() {
    try {
      const d = await getJSON('/api/audit-logs?limit=8');
      const box = $('audit-chain');
      if (!box) return;
      box.innerHTML = (d.logs || []).slice(0, 8).map(l =>
        `<div class="hash" title="${esc(l.status)} · ${esc(l.trace_hash)}"><small>${esc(l.module)} · ${esc(String(l.action).replace(/_/g, ' ').toLowerCase())}</small><b>#${esc(l.trace_hash.slice(0, 6))}</b></div>`).join('');
    } catch (e) { /* ignore */ }
  }

  function refreshSide() { loadVaults(); loadApprovals(); loadAudit(); loadNotifications(); }

  /* ---------- approvals & inline actions ---------- */
  async function decide(id, approve, quiz, otp) {
    const L = T();
    try {
      const d = await getJSON(`/api/agent/approvals/${id}/decide`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ approve, quiz_answers: quiz, otp: otp || null })
      });
      const cls = d.status === 'APPROVED' ? 'ok' : (d.status === 'PENDING' ? 'regen' : 'flag');
      const head = d.status === 'APPROVED' ? '✓ ' + L.done : d.status === 'PENDING' ? '⏳ ' + L.stillWaiting : '✕ ' + L.cancelled;
      const detail = d.status === 'APPROVED' ? '' : (d.message || '');
      addNote(`<span class="${cls}">${esc(head)}</span> ${esc(detail)}`);
      toast(`${head} ${detail}`.trim());

      if (d.status === 'APPROVED' || d.status === 'REJECTED') {
        document.querySelectorAll(`[data-req-box="${id}"]`).forEach(el => {
          el.classList.add('resolved');
          const btns = el.querySelector('.ia-btns');
          if (btns) btns.innerHTML = `<span class="${cls}">${esc(head)}</span>`;
        });
      }
      refreshSide();
    } catch (e) {
      toast(`${L.requestFailed} ${e.message}`);
    }
  }

  async function openQuiz(id, untilIso) {
    const L = T();
    const untilMs = untilIso ? new Date(untilIso).getTime() : 0;
    const remSec = Math.max(0, Math.round((untilMs - Date.now()) / 1000));
    if (remSec > 0) {
      toast(L.waitCooling(remSec));
      addNote(`<span class="regen">⏳ ${esc(L.waitCooling(remSec))}</span>`);
      return;
    }

    const q = await getJSON('/api/agent/quiz');
    const form = $('quiz-form');
    form.innerHTML = `<h3>🛡️ ${esc(L.quizTitle)}</h3><p class="quiz-intro">${esc(L.quizIntro)}</p>` +
      q.questions.map((qq, i) => `<fieldset><legend>${i + 1}. ${esc(qq.question)}</legend>${qq.options.map((o, j) =>
        `<label><input type="radio" name="q${i}" value="${j}" required> <span>${esc(o)}</span></label>`).join('')}</fieldset>`).join('') +
      `<div class="quiz-actions">
        <button class="btn primary" type="submit">${esc(L.quizSubmit)}</button>
        <button class="btn secondary" type="button" id="quiz-cancel">${esc(L.quizCancel)}</button>
      </div>`;
    form.onsubmit = (e) => {
      e.preventDefault();
      const ans = q.questions.map((_, i) => Number(form[`q${i}`].value));
      $('quiz-modal').classList.remove('show');
      askOtp(id, ans);
    };
    $('quiz-cancel').onclick = () => $('quiz-modal').classList.remove('show');
    $('quiz-modal').classList.add('show');
  }

  /* one-time code step for every approval (Tier 3 policy); the sandbox shows the simulated SMS on screen */
  async function askOtp(id, quiz) {
    const L = T();
    let sms;
    try {
      sms = await getJSON(`/api/agent/approvals/${id}/otp`, { method: 'POST' });
    } catch (e) {
      toast(`${L.requestFailed} ${e.message}`);
      return;
    }
    const form = $('quiz-form');
    form.innerHTML = `<h3>🔐 ${esc(L.otpTitle)}</h3><p class="quiz-intro">${esc(L.otpIntro)}</p>
      <div class="otp-sms">${esc(sms.message)}</div>
      <input class="otp-input" id="otp-input" inputmode="numeric" autocomplete="one-time-code" maxlength="6" pattern="[0-9]{6}" required placeholder="••••••">
      <div class="quiz-actions">
        <button class="btn primary" type="submit">${esc(L.otpConfirm)}</button>
        <button class="btn secondary" type="button" id="quiz-cancel">${esc(L.quizCancel)}</button>
      </div>`;
    form.onsubmit = (e) => {
      e.preventDefault();
      $('quiz-modal').classList.remove('show');
      decide(id, true, quiz, $('otp-input').value);
    };
    $('quiz-cancel').onclick = () => $('quiz-modal').classList.remove('show');
    $('quiz-modal').classList.add('show');
    setTimeout(() => { const i = $('otp-input'); if (i) i.focus(); }, 50);
  }

  /* ---------- notifications (simulated push) ---------- */
  let lastNotifId = null;
  async function loadNotifications() {
    try {
      const d = await getJSON('/api/notifications?limit=20');
      const L = T();
      const items = d.items || [];
      const badge = $('notif-badge');
      if (badge) { badge.hidden = !d.unread; badge.textContent = d.unread; }
      const list = $('notif-list');
      if (list) {
        list.classList.toggle('empty', !items.length);
        list.innerHTML = items.length ? items.map(n => `
          <div class="notif-item"><b>${esc(n.title)}</b>${esc(n.body)}<br><small>${esc(n.at.slice(11, 19))} · ${esc(n.tier)} · ${esc(n.channel)}</small></div>`).join('')
          : esc(L.notifEmpty);
      }
      const newest = items.length ? items[0].id : 0;
      if (lastNotifId !== null) {
        items.filter(n => n.id > lastNotifId).reverse().forEach(n => toast(`${L.push} ${n.title}: ${n.body}`));
      }
      lastNotifId = Math.max(lastNotifId || 0, newest);
    } catch (e) { /* ignore */ }
  }

  async function toggleNotifications() {
    const panel = $('notif-panel');
    if (!panel) return;
    panel.hidden = !panel.hidden;
    if (!panel.hidden) {
      $('notif-title').textContent = T().notifTitle;
      await loadNotifications();
      try { await getJSON('/api/notifications/read', { method: 'POST' }); } catch (e) { /* ignore */ }
      const badge = $('notif-badge');
      if (badge) badge.hidden = true;
    }
  }

  /* ---------- guardian intercept ---------- */
  function friendlyEvidence(e) {
    const L = T();
    const m = /^Matched pattern '([a-z_]+)'$/.exec(e);
    if (m) return L.evidence[m[1]] || m[1].replace(/_/g, ' ');
    if (/never been paid before/.test(e)) return L.evidence.new_payee;
    return e;
  }

  function showIntercept(g, reqId) {
    const L = T();
    const risk = Math.round(g.risk_score);
    const r = 34, c = 2 * Math.PI * r;
    $('gauge-arc').setAttribute('stroke-dasharray', `${(risk / 100) * c} ${c}`);
    $('gauge-arc').setAttribute('stroke', '#ffffff');
    $('gauge-text').textContent = risk;
    $('intercept-title').textContent = L.frozenTitle;
    $('intercept-lede').textContent = L.frozenLede;
    $('intercept-saw-h').textContent = L.sawH;
    $('intercept-know-h').textContent = L.knowH;
    $('intercept-close').textContent = L.review;
    if ($('intercept-speak')) $('intercept-speak').textContent = '🔊 ' + L.readAloud;
    $('intercept-kind').textContent = L.scam[g.scam_type] || String(g.scam_type || 'suspicious transfer').replace(/_/g, ' ');
    $('intercept-evidence').innerHTML = (g.evidence || []).map(e => `<li>${esc(friendlyEvidence(e))}</li>`).join('') || `<li>${esc(L.behaviourOnly)}</li>`;
    $('intercept-facts').innerHTML = (g.counter_facts || []).map(e => `<li>${esc(e)}</li>`).join('');
    $('intercept-actions').textContent = (g.recommended_actions || []).join(' · ');
    $('guardian-overlay').classList.add('show');
    let s = g.cooling_off_seconds || 60;
    const el = $('intercept-countdown');
    el.textContent = L.coolingShort(s);
    const iv = setInterval(() => {
      s -= 1;
      el.textContent = s > 0 ? T().coolingShort(s) : T().coolingOver;
      if (s <= 0) clearInterval(iv);
    }, 1000);
  }

  /* ---------- click delegation for approvals & inline chat buttons ---------- */
  function handleActionClick(e) {
    const approveBtn = e.target.closest('[data-approve]');
    if (approveBtn) {
      const id = approveBtn.dataset.approve;
      const needsQuiz = approveBtn.dataset.quiz === 'true';
      const until = approveBtn.dataset.until || '';
      if (needsQuiz) openQuiz(id, until);
      else askOtp(id, null);
      return;
    }

    const rejectBtn = e.target.closest('[data-reject]');
    if (rejectBtn) {
      decide(rejectBtn.dataset.reject, false, null);
      return;
    }

    const cancelSubBtn = e.target.closest('[data-cancel-sub]');
    if (cancelSubBtn) {
      const merchant = cancelSubBtn.dataset.cancelSub;
      cancelSubBtn.disabled = true;
      send(`cancel my ${merchant} subscription`);
    }
  }

  /* ---------- wiring ---------- */
  document.addEventListener('DOMContentLoaded', () => {
    loadHealth();
    refreshSide();
    const composer = $('composer');
    if (composer) {
      composer.addEventListener('submit', (e) => {
        e.preventDefault();
        const i = $('input');
        const v = i.value;
        i.value = '';
        send(v);
      });
    }
    document.querySelectorAll('.quick button').forEach(b => b.addEventListener('click', () => send(b.dataset.q)));
    const attachBtn = $('attach');
    if (attachBtn) attachBtn.addEventListener('click', () => $('file').click());
    const fileInput = $('file');
    if (fileInput) {
      fileInput.addEventListener('change', (e) => {
        attachment = e.target.files[0];
        if (attachment && $('attach')) $('attach').textContent = '📎 ' + attachment.name;
      });
    }
    if (Recognition && $('voice')) {
      $('voice').hidden = false;
      const micLang = $('mic-lang');
      let micLangChosen = false;
      const followUi = () => { if (!micLangChosen) micLang.value = window.SG_LANG === 'vi' ? 'vi-VN' : 'en-US'; };
      followUi();
      micLang.addEventListener('change', () => { micLangChosen = true; });
      document.addEventListener('sg:lang', () => { followUi(); micLabel(mic.wanted); });
      $('mic').addEventListener('click', toggleMic);
      micLabel(false);
    }
    const appBox = $('approvals');
    if (appBox) appBox.addEventListener('click', handleActionClick);
    const convBox = $('conversation');
    if (convBox) {
      convBox.addEventListener('click', handleActionClick);
      convBox.addEventListener('click', (e) => {
        const b = e.target.closest('[data-speak]');
        if (!b) return;
        const bubble = b.closest('.msg') && b.closest('.msg').querySelector('.bubble');
        if (bubble) speak(bubble.innerText, b);
      });
    }
    const interceptSpeak = $('intercept-speak');
    if (interceptSpeak && canSpeak) {
      interceptSpeak.hidden = false;
      interceptSpeak.addEventListener('click', () => {
        const parts = ['intercept-title', 'intercept-kind', 'intercept-lede', 'intercept-saw-h', 'intercept-evidence',
                       'intercept-know-h', 'intercept-facts'].map(id => ($(id) ? $(id).innerText : ''))
          .map(t => t.replace(/\s*\n\s*/g, '. ').replace(/[.\s]+$/, '')).filter(Boolean);
        speak(parts.join('. ') + '.', interceptSpeak);
      });
    }
    const interceptClose = $('intercept-close');
    if (interceptClose) {
      interceptClose.addEventListener('click', () => {
        $('guardian-overlay').classList.remove('show');
        if (canSpeak) window.speechSynthesis.cancel();
        const appCard = document.querySelector('.card-approvals');
        if (appCard) appCard.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      });
    }
    const toolsToggle = $('tools-toggle');
    if (toolsToggle) toolsToggle.addEventListener('click', () => $('drawer').classList.toggle('open'));
    const resetRailBtn = $('reset-rail');
    if (resetRailBtn) resetRailBtn.addEventListener('click', resetRail);
    const themeBtn = $('theme-toggle');
    if (themeBtn) themeBtn.addEventListener('click', toggleTheme);
    const bell = $('notif-bell');
    if (bell) bell.addEventListener('click', toggleNotifications);
    document.addEventListener('sg:lang', refreshSide);
    document.addEventListener('keydown', (e) => {
      if (e.key !== 'Escape') return;
      $('drawer').classList.remove('open');
      if ($('notif-panel')) $('notif-panel').hidden = true;
    });
    setInterval(loadAudit, 15000);
  });
})();
