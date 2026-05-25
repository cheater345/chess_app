const socket = io();
let board = null, analysisBoard = null, puzzleBoard = null, replayBoard = null;
let currentGameId = null, myColor = null, gameState = null, gameOver = false;
let selectedElo = 'intermediate', selectedAiDifficulty = 'intermediate';
let drawOffered = false, myRating = 1200, selectedSquare = null, aiThinking = false, isAiGame = false;
let selectedTimeControl = 300, whiteTimer = 300, blackTimer = 300;
let timerInterval = null, timerActiveColor = null, timerStartTime = null, timerStartValue = 0;
let currentPuzzle = null, puzzleMoves = [], puzzleIndex = 0, puzzleSolved = false;
let analysisMoves = [], analysisIndex = 0;
let replayMoves = [], replayIndex = 0;
let soundEnabled = true, zenMode = false, currentPieceSet = 'wikipedia', currentBoardTheme = 'classic';
let isAuthenticated = false;

const ELO_MAP = {beginner:{rating:600,label:'Beginner',range:'400-800'},intermediate:{rating:1200,label:'Intermediate',range:'800-1400'},advanced:{rating:1800,label:'Advanced',range:'1400-2000'},master:{rating:2200,label:'Master',range:'2000-2400'},grandmaster:{rating:2600,label:'Grandmaster',range:'2400+'}};
const AI_ELO_MAP = {beginner:{rating:600,label:'Beginner'},intermediate:{rating:1200,label:'Intermediate'},advanced:{rating:1800,label:'Advanced'},master:{rating:2200,label:'Master'},grandmaster:{rating:2600,label:'Grandmaster'}};
const PIECE_UNICODE = {'P':'♙','N':'♘','B':'♗','R':'♖','Q':'♕','K':'♔','p':'♟','n':'♞','b':'♝','r':'♜','q':'♛','k':'♚'};

const PIECE_SETS = {wikipedia:'https://chessboardjs.com/img/chesspieces/wikipedia/{piece}.png',alpha:'https://chessboardjs.com/img/chesspieces/alpha/{piece}.png',uscf:'https://chessboardjs.com/img/chesspieces/uscf/{piece}.png',maya:'https://chessboardjs.com/img/chesspieces/maya/{piece}.png'};
const BOARD_THEMES = {classic:{light:'#f0d9b5',dark:'#b58863'},green:{light:'#b8c48a',dark:'#7a9450'},blue:{light:'#dee3e6',dark:'#6b8fbb'},ice:{light:'#e8edf3',dark:'#5b7d9a'},dark:{light:'#b0b0b0',dark:'#404040'},wood:{light:'#ebd0a3',dark:'#c89b5e'}};

const AudioCtx = window.AudioContext || window.webkitAudioContext;
let audioCtx = null;
function playSound(type){
  if(!soundEnabled)return;
  if(!audioCtx)audioCtx=new AudioCtx();
  const osc=audioCtx.createOscillator(),gain=audioCtx.createGain();
  osc.connect(gain);gain.connect(audioCtx.destination);
  gain.gain.value=0.08;osc.type='sine';
  const now=audioCtx.currentTime;
  if(type==='move'){osc.frequency.setValueAtTime(400,now);osc.frequency.exponentialRampToValueAtTime(600,now+0.08);gain.gain.exponentialRampToValueAtTime(0.001,now+0.12);osc.start(now);osc.stop(now+0.12);}
  else if(type==='capture'){osc.frequency.setValueAtTime(300,now);osc.frequency.exponentialRampToValueAtTime(150,now+0.1);gain.gain.exponentialRampToValueAtTime(0.001,now+0.15);osc.start(now);osc.stop(now+0.15);}
  else if(type==='check'){osc.frequency.setValueAtTime(600,now);osc.frequency.setValueAtTime(400,now+0.1);osc.frequency.setValueAtTime(600,now+0.2);gain.gain.exponentialRampToValueAtTime(0.001,now+0.3);osc.start(now);osc.stop(now+0.3);}
  else if(type==='gameover'){osc.frequency.setValueAtTime(500,now);osc.frequency.setValueAtTime(700,now+0.15);osc.frequency.setValueAtTime(900,now+0.3);gain.gain.exponentialRampToValueAtTime(0.001,now+0.5);osc.start(now);osc.stop(now+0.5);}
  else if(type==='error'){osc.type='sawtooth';osc.frequency.setValueAtTime(200,now);osc.frequency.exponentialRampToValueAtTime(100,now+0.15);gain.gain.exponentialRampToValueAtTime(0.001,now+0.2);osc.start(now);osc.stop(now+0.2);}
}

// ======== NAVIGATION ========
function switchToView(viewName){
  document.querySelectorAll('.view').forEach(v=>v.classList.remove('active'));
  document.querySelectorAll('.nav-link').forEach(l=>l.classList.remove('active'));
  const viewEl = document.getElementById(viewName + 'View');
  if(viewEl)viewEl.classList.add('active');
  const navLink = document.querySelector(`.nav-link[data-view="${viewName}"]`);
  if(navLink)navLink.classList.add('active');
  if(viewEl && board)board.resize();
}

document.querySelectorAll('.nav-link[data-view]').forEach(link=>{
  link.addEventListener('click',e=>{
    e.preventDefault();
    const view = link.dataset.view;
    if(view==='lobby'){switchToView('lobby');closeGame();}
    else switchToView(view);
    if(view==='leaderboard')loadLeaderboard();
    if(view==='puzzles'&&!currentPuzzle)getNewPuzzle();
  });
});

document.addEventListener('click',e=>{
  if(!e.target.closest('.user-menu'))document.getElementById('userDropdown')?.classList.add('hidden');
  if(e.target.classList.contains('modal-backdrop'))e.target.closest('.modal')?.classList.add('hidden');
});

// ======== AUTH ========
function showAuthModal(){
  document.getElementById('authModal').classList.remove('hidden');
  document.getElementById('userDropdown')?.classList.add('hidden');
}
function closeAuthModal(){document.getElementById('authModal').classList.add('hidden');}
function switchAuthTab(tab){
  document.querySelectorAll('.auth-tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===tab));
  document.getElementById('authEmail').classList.toggle('hidden',tab==='login');
  const btn=document.querySelector('#authModal .btn-play');
  btn.textContent=tab==='login'?'Log In':'Register';
}
function submitAuth(){
  const tab=document.querySelector('.auth-tab.active')?.dataset.tab||'login';
  const username=document.getElementById('authUsername').value.trim();
  const email=tab==='register'?document.getElementById('authEmail').value.trim():'';
  const password=document.getElementById('authPassword').value;
  const errorEl=document.getElementById('authError');
  if(!username||!password||(tab==='register'&&!email)){errorEl.textContent='All fields required';return;}
  errorEl.textContent='';
  const url=tab==='login'?'/api/login':'/api/register';
  fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,email,password})})
  .then(r=>r.json()).then(d=>{
    if(d.error){errorEl.textContent=d.error;return;}
    isAuthenticated=true;
    myRating=d.rating;
    sessionStorage.setItem('auth','true');
    closeAuthModal();
    updateUserUI(d.username,d.rating);
    showNotification(`Welcome, ${d.username}!`,'success');
    loadUserStats();
  }).catch(()=>errorEl.textContent='Connection error');
}
function continueAsGuest(){
  fetch('/api/guest',{method:'GET'}).then(r=>r.json()).then(d=>{
    closeAuthModal();
    updateUserUI(d.username,1200);
  });
}
function logout(){
  fetch('/api/logout').then(r=>r.json()).then(()=>{
    isAuthenticated=false;
    sessionStorage.removeItem('auth');
    document.getElementById('userDropdown')?.classList.add('hidden');
    updateUserUI('Guest',1200);
    document.getElementById('loginDropdownBtn').textContent='Log In';
    document.getElementById('logoutBtn').classList.add('hidden');
    showNotification('Logged out','info');
    loadUserStats();
  });
}
function toggleUserDropdown(){
  const dd=document.getElementById('userDropdown');
  dd.classList.toggle('hidden');
  if(!dd.classList.contains('hidden')){
    if(isAuthenticated){
      document.getElementById('loginDropdownBtn').classList.add('hidden');
      document.getElementById('logoutBtn').classList.remove('hidden');
    }else{
      document.getElementById('loginDropdownBtn').classList.remove('hidden');
      document.getElementById('logoutBtn').classList.add('hidden');
    }
  }
}
function updateUserUI(username,rating){
  document.getElementById('usernameDisplay').textContent=username;
  document.getElementById('navbarRating').textContent=rating;
  document.getElementById('navbarAvatar').textContent=username.charAt(0).toUpperCase();
  document.getElementById('lobbyRating').textContent=rating;
  myRating=rating;
}

// ======== PROFILE ========
function showProfile(username){
  if(!username&&!isAuthenticated){showAuthModal();return;}
  const u=username||document.getElementById('usernameDisplay').textContent;
  switchToView('profile');
  fetch('/api/profile/'+encodeURIComponent(u)).then(r=>r.json()).then(d=>{
    if(d.error){showNotification(d.error,'error');return;}
    document.getElementById('profileAvatarLarge').textContent=d.username.charAt(0).toUpperCase();
    document.getElementById('profileUsername').textContent=d.username;
    document.getElementById('profileRating').textContent='Rating: '+d.rating;
    document.getElementById('profileGames').textContent=d.total_games;
    document.getElementById('profileWins').textContent=d.wins;
    document.getElementById('profileLosses').textContent=d.losses;
    document.getElementById('profileDraws').textContent=d.draws;
    document.getElementById('profileWinRate').textContent=d.win_rate+'%';
    document.getElementById('profileStreak').textContent=d.max_streak;
    document.getElementById('profilePuzzleRating').textContent=d.puzzle_rating;
    document.getElementById('profilePuzzlesSolved').textContent=d.puzzles_solved;
    loadRecentGames(u);
  }).catch(()=>showNotification('Failed to load profile','error'));
}
function loadRecentGames(username){
  fetch('/api/games/'+encodeURIComponent(username)).then(r=>r.json()).then(games=>{
    const el=document.getElementById('recentGames');
    if(!games||games.length===0){el.innerHTML='<div class="games-empty">No games played yet</div>';return;}
    el.innerHTML=games.map(g=>{
      const isWin=g.winner==='white'?g.white===username:g.winner==='black'?g.black===username:null;
      const resultClass=isWin===true?'green':isWin===false?'red':'';
      const resultText=isWin===true?'Won':isWin===false?'Lost':'Draw';
      return `<div class="recent-game-item" onclick="openGameReplay('${g.game_id}')">
        <span>${g.white} vs ${g.black}</span>
        <span style="color:var(--${resultClass||'text3'})">${resultText}</span>
        <span style="color:var(--text3);font-size:11px">${g.time_control/60}min</span>
      </div>`;
    }).join('');
  });
}

// ======== SETTINGS ========
function showSettings(){document.getElementById('settingsModal').classList.remove('hidden');document.getElementById('userDropdown')?.classList.add('hidden');}
function closeSettings(){document.getElementById('settingsModal').classList.add('hidden');}
function selectBoardTheme(theme){
  currentBoardTheme=theme;
  document.querySelectorAll('#boardThemeOptions .theme-option').forEach(o=>o.classList.toggle('active',o.dataset.theme===theme));
  applyBoardTheme(theme);
  if(isAuthenticated)fetch('/api/user/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({board_theme:theme})});
}
function applyBoardTheme(theme){
  const t=BOARD_THEMES[theme]||BOARD_THEMES.classic;
  const style=document.getElementById('board-theme-style');
  if(style)style.textContent=`.chess-board .board-b72b1 .square-55d63.light-1e7{background:${t.light}!important}.chess-board .board-b72b1 .square-55d63.dark-1e7{background:${t.dark}!important}`;
}
function selectPieceSet(set){
  currentPieceSet=set;
  document.querySelectorAll('#pieceSetOptions .theme-option').forEach(o=>o.classList.toggle('active',o.dataset.set===set));
  if(isAuthenticated)fetch('/api/user/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({piece_set:set})});
  if(board)board.destroy();board=null;if(gameViewActive())initBoard();
}
function toggleSound(){
  soundEnabled=document.getElementById('soundToggle').checked;
  if(isAuthenticated)fetch('/api/user/settings',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({sound_enabled:soundEnabled})});
}

// ======== ELO & TIME SELECTION ========
function selectElo(level){selectedElo=level;document.querySelectorAll('#eloGrid .elo-card').forEach(c=>c.classList.remove('selected'));document.querySelector(`#eloGrid .elo-card[data-elo="${level}"]`).classList.add('selected');myRating=ELO_MAP[level].rating;document.getElementById('lobbyRating').textContent=myRating;document.getElementById('navbarRating').textContent=myRating;}
function selectAiDifficulty(level){selectedAiDifficulty=level;document.querySelectorAll('#aiEloGrid .elo-card').forEach(c=>c.classList.remove('selected'));document.querySelector(`#aiEloGrid .elo-card[data-elo="${level}"]`).classList.add('selected');}
function selectTimeControl(s){selectedTimeControl=s;document.querySelectorAll('.tc-btn').forEach(b=>b.classList.remove('tc-active'));document.querySelector(`.tc-btn[data-tc="${s}"]`).classList.add('tc-active');}

// ======== LOBBY ACTIONS ========
function playComputer(){socket.emit('create_ai_game',{difficulty:selectedAiDifficulty,rating:ELO_MAP[selectedElo].rating,time_control:selectedTimeControl});}
function findMatch(){socket.emit('find_match',{elo:selectedElo,rating:myRating,time_control:selectedTimeControl});}
function cancelSearch(){socket.emit('cancel_search');document.getElementById('searchStatus').classList.add('hidden');}
function createGame(){socket.emit('create_game',{elo:selectedElo,rating:myRating,time_control:selectedTimeControl});}
function joinGame(){const code=document.getElementById('gameCodeInput').value.trim().toLowerCase();if(!code)return showNotification('Enter a game code','error');if(code.length<3)return showNotification('Invalid game code','error');socket.emit('join_game',{game_id:code,elo:selectedElo,rating:myRating,time_control:selectedTimeControl});}

// ======== TIMER ========
function formatTimer(s){const m=Math.floor(Math.max(0,s)/60);const sec=Math.floor(Math.max(0,s)%60);return m+':'+(sec<10?'0':'')+sec;}
function getTimerValue(color){if(timerActiveColor===color&&timerStartTime!==null){const elapsed=(Date.now()-timerStartTime)/1000;return Math.max(0,timerStartValue-elapsed);}return color==='white'?whiteTimer:blackTimer;}
function updateTimerDisplay(){
  const oppTimer=myColor==='white'?getTimerValue('black'):getTimerValue('white');
  const myT=myColor==='white'?getTimerValue('white'):getTimerValue('black');
  ['opponent','my'].forEach((p,i)=>{
    const el=document.getElementById(p+'Timer');
    if(!el)return;
    const v=i===0?oppTimer:myT;
    el.textContent=formatTimer(v);
    el.className='pb-timer'+(v<=10?' zero-time':v<=30?' low-time':'');
  });
}
function startTimerCountdown(){stopTimerCountdown();if(!timerActiveColor)return;timerStartTime=Date.now();timerStartValue=timerActiveColor==='white'?whiteTimer:blackTimer;updateTimerDisplay();timerInterval=setInterval(updateTimerDisplay,100);}
function stopTimerCountdown(){if(timerInterval){clearInterval(timerInterval);timerInterval=null;}timerStartTime=null;}

// ======== SOCKET EVENTS ========
socket.on('connect',()=>{});
socket.on('game_created',d=>{currentGameId=d.game_id;myColor=d.color;gameState=d.state;isAiGame=false;enterGame();});
socket.on('ai_game_started',d=>{currentGameId=d.game_id;myColor=d.color;gameState=d.state;isAiGame=true;enterGame();});
socket.on('game_joined',d=>{myColor=d.color;gameState=d.state;isAiGame=false;enterGame();});
socket.on('opponent_joined',d=>{gameState=d.state;updateUI();});
socket.on('match_found',d=>{currentGameId=d.game_id;myColor=d.color;gameState=d.state;isAiGame=false;document.getElementById('searchStatus').classList.add('hidden');showNotification('Match found!','success');enterGame();});
socket.on('searching',()=>{document.getElementById('searchStatus').classList.remove('hidden');});
socket.on('ai_thinking',()=>{aiThinking=true;updateStatus();});

socket.on('move_made',d=>{
  const wasAiThinking=aiThinking;gameState=d.state;const wasOver=gameOver;gameOver=gameState.status==='finished';aiThinking=false;selectedSquare=null;
  if(gameState.timers){whiteTimer=gameState.timers.white;blackTimer=gameState.timers.black;}
  timerActiveColor=gameOver?null:gameState.turn;
  if(gameOver){stopTimerCountdown();playSound('gameover');}else{startTimerCountdown();if(gameState.in_check)playSound('check');else playSound('move');}
  updateUI();
  if(gameState.is_ai&&!gameOver&&gameState.turn!==myColor){aiThinking=true;updateStatus();}
  if(gameOver&&!wasOver&&gameState.result){setTimeout(()=>showGameOver(gameState.result),600);}
});

socket.on('move_error',d=>{showNotification(d.message,'error');playSound('error');if(gameState&&board)board.position(gameState.fen);});

socket.on('game_over',d=>{
  gameState=d.state;gameOver=true;aiThinking=false;selectedSquare=null;stopTimerCountdown();
  if(gameState.timers){whiteTimer=gameState.timers.white;blackTimer=gameState.timers.black;}
  updateUI();playSound('gameover');setTimeout(()=>showGameOver(d.result),600);
});

socket.on('opponent_disconnected',()=>{gameOver=true;aiThinking=false;showNotification('Opponent disconnected','error');setTimeout(()=>showGameOver('Opponent disconnected'),600);});
socket.on('draw_offered',()=>{drawOffered=true;showNotification('Opponent offers a draw','info');showDrawDialog();});
socket.on('draw_declined',()=>{drawOffered=false;showNotification('Draw declined','info');});

socket.on('rematch_started',d=>{
  currentGameId=d.game_id;myColor=d.color;gameState=d.state;gameOver=false;drawOffered=false;aiThinking=false;selectedSquare=null;isAiGame=gameState.is_ai||false;stopTimerCountdown();
  if(gameState&&gameState.timers){whiteTimer=gameState.timers.white;blackTimer=gameState.timers.black;}
  timerActiveColor=gameState?gameState.turn:null;closeModal();if(board){board.destroy();board=null;}enterGame();showNotification('Rematch started!','success');
});
socket.on('lobby_update',d=>updateLobbyGames(d));
socket.on('error',d=>showNotification(d.message,'error'));

socket.on('legal_moves',d=>{
  const moves=d.moves||[],wrapper=document.getElementById('chessBoard');
  if(!wrapper)return;
  moves.forEach(m=>{
    const toEl=wrapper.querySelector(`[data-square="${m.to}"]`);
    if(!toEl)return;
    const pos=board.position();
    if(pos[m.to])toEl.classList.add('highlight-capture');
    else toEl.classList.add('highlight-move');
  });
});

socket.on('chat_message',d=>{
  const el=document.getElementById('chatMessages');
  if(!el)return;
  const msg=document.createElement('div');msg.className='chat-msg';
  msg.innerHTML=`<span class="chat-user">${escapeHtml(d.username)}:</span> <span class="chat-text">${escapeHtml(d.message)}</span>`;
  el.appendChild(msg);el.scrollTop=el.scrollHeight;
});
socket.on('chat_history',msgs=>{
  const el=document.getElementById('chatMessages');if(!el)return;el.innerHTML='';
  msgs.forEach(m=>{
    const msg=document.createElement('div');msg.className='chat-msg';
    msg.innerHTML=`<span class="chat-user">${escapeHtml(m.username)}:</span> <span class="chat-text">${escapeHtml(m.message)}</span>`;
    el.appendChild(msg);
  });
  el.scrollTop=el.scrollHeight;
});

function escapeHtml(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML;}
function uciToMove(uci){return{from:uci.slice(0,2),to:uci.slice(2,4),promotion:uci.length>4?uci[4]:undefined};}

// ======== DRAW DIALOG ========
function showDrawDialog(){
  const existing=document.querySelector('.draw-dialog');if(existing)existing.remove();
  const div=document.createElement('div');div.className='draw-dialog';
  div.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#272522;padding:28px;border-radius:12px;z-index:1500;box-shadow:0 8px 32px rgba(0,0,0,0.5);text-align:center;';
  div.innerHTML=`<h3 style="margin-bottom:14px;font-size:16px;">Opponent offers a draw</h3><div style="display:flex;gap:10px;justify-content:center;"><button class="btn btn-play" onclick="acceptDraw()">Accept</button><button class="btn btn-secondary" onclick="declineDraw()">Decline</button></div>`;
  document.body.appendChild(div);
}
function acceptDraw(){document.querySelector('.draw-dialog')?.remove();socket.emit('accept_draw',{game_id:currentGameId});}
function declineDraw(){document.querySelector('.draw-dialog')?.remove();socket.emit('decline_draw',{game_id:currentGameId});drawOffered=false;}

// ======== CHAT ========
function toggleChat(){document.getElementById('chatBody').classList.toggle('collapsed');}
function sendChat(){
  const input=document.getElementById('chatInput');
  const msg=input.value.trim();
  if(!msg||!currentGameId)return;
  socket.emit('send_chat',{game_id:currentGameId,message:msg});
  input.value='';
}
document.getElementById('chatInput')?.addEventListener('keydown',e=>{if(e.key==='Enter')sendChat();});

// ======== GAME ENTRY ========
function enterGame(){
  switchToView('game');
  document.getElementById('rematchBtn').classList.add('hidden');
  document.getElementById('leaveBtn').classList.add('hidden');
  document.getElementById('drawBtn').classList.toggle('hidden',isAiGame);
  document.getElementById('analyzeBtn').classList.add('hidden');
  closeModal();gameOver=false;drawOffered=false;aiThinking=false;selectedSquare=null;stopTimerCountdown();
  if(gameState&&gameState.timers){whiteTimer=gameState.timers.white;blackTimer=gameState.timers.black;}
  else{whiteTimer=selectedTimeControl;blackTimer=selectedTimeControl;}
  timerActiveColor=gameState?gameState.turn:null;
  if(!gameOver&&gameState)startTimerCountdown();
  initBoard();updateUI();
  if(isAiGame&&gameState&&gameState.turn!==myColor){aiThinking=true;updateStatus();}
  socket.emit('get_chat_history',{game_id:currentGameId});
  document.getElementById('chatBody').classList.remove('collapsed');
}
function gameViewActive(){return document.getElementById('gameView').classList.contains('active');}

function initBoard(){
  const orientation=myColor==='black'?'black':'white';
  const cfg={pieceTheme:PIECE_SETS[currentPieceSet]||PIECE_SETS.wikipedia,position:gameState?gameState.fen:'start',draggable:false,orientation:orientation,showErrors:false};
  if(board){board.destroy();}
  board=Chessboard('chessBoard',cfg);
  window.addEventListener('resize',()=>{if(board)board.resize();});
  initClickHandlers();
  applyBoardTheme(currentBoardTheme);
}

// ======== CLICK-TO-CLICK ========
function initClickHandlers(){
  $(document).off('click','#chessBoard [data-square]');
  $(document).on('click','#chessBoard [data-square]',function(){handleSquareClick($(this).data('square'));});
}
function handleSquareClick(square){
  if(gameOver)return;
  if(!gameState||gameState.turn!==myColor)return;
  removeHighlights();
  const pos=board.position(),piece=pos[square];
  const isMyPiece=piece&&piece[0]===(myColor==='white'?'w':'b');
  if(square===selectedSquare){selectedSquare=null;return;}
  if(selectedSquare){
    let move=selectedSquare+square;
    const p=pos[selectedSquare];
    if(p&&p[1]==='P'&&((myColor==='white'&&square[1]==='8')||(myColor==='black'&&square[1]==='1')))move+='q';
    selectedSquare=null;
    socket.emit('make_move',{game_id:currentGameId,move});
    return;
  }
  if(isMyPiece){selectedSquare=square;highlightSquare(square);socket.emit('get_legal_moves',{game_id:currentGameId,square});}
}
function highlightSquare(s){const el=document.querySelector(`#chessBoard [data-square="${s}"]`);if(el)el.classList.add('square-selected');}
function removeHighlights(){document.querySelectorAll('.highlight-hint,.highlight-move,.highlight-capture,.square-selected').forEach(el=>el.classList.remove('highlight-hint','highlight-move','highlight-capture','square-selected'));document.querySelectorAll('[style*="cursor"]').forEach(el=>el.style.cursor='');}

// ======== UI UPDATE ========
function updateUI(){
  if(!gameState)return;
  if(board)board.position(gameState.fen,false);
  const oppColor=myColor==='white'?'black':'white';
  document.getElementById('opponentName').textContent=gameState[oppColor+'_name']||'Opponent';
  document.getElementById('myName').textContent=gameState[myColor+'_name']||'You';
  document.getElementById('opponentRating').textContent=gameState[oppColor+'_rating']||'—';
  document.getElementById('myRating').textContent=gameState[myColor+'_rating']||myRating;
  document.getElementById('opponentBar').classList.toggle('active-turn',gameState.turn===oppColor&&!gameOver);
  document.getElementById('myBar').classList.toggle('active-turn',gameState.turn===myColor&&!gameOver);
  updateCaptured();updateMoveHistory();updateStatus();updateTimerDisplay();
}
function updateCaptured(){
  const wCap=(gameState.captured_white||[]).map(p=>PIECE_UNICODE[p]||p).join(' ');
  const bCap=(gameState.captured_black||[]).map(p=>PIECE_UNICODE[p]||p).join(' ');
  document.getElementById('opponentCaptured').textContent=myColor==='black'?wCap:bCap;
  document.getElementById('myCaptured').textContent=myColor==='white'?wCap:bCap;
}
function updateMoveHistory(){
  const container=document.getElementById('moveHistory'),moves=gameState.move_history||[];
  container.innerHTML='';
  for(let i=0;i<moves.length;i+=2){
    const row=document.createElement('div');row.className='move-row';
    const num=document.createElement('span');num.className='move-num';num.textContent=Math.floor(i/2)+1+'.';row.appendChild(num);
    const w=document.createElement('span');w.className='move-w';w.textContent=moves[i];row.appendChild(w);
    const b=document.createElement('span');b.className='move-b';b.textContent=moves[i+1]||'';row.appendChild(b);
    container.appendChild(row);
  }
  container.scrollTop=container.scrollHeight;
  const resultEl=document.getElementById('moveResult');
  if(gameOver&&gameState.result)resultEl.textContent=gameState.result;
  else resultEl.textContent='';
}
function updateStatus(){
  const el=document.getElementById('gameStatus');
  if(!gameState){el.textContent='Waiting...';return;}
  if(gameOver){el.textContent='Game Over';el.style.color='var(--gold)';return;}
  if(aiThinking){el.textContent='AI thinking...';el.style.color='var(--gold)';return;}
  if(gameState.in_check){el.textContent=(gameState.turn==='white'?'White':'Black')+' is in check!';el.style.color='var(--red)';return;}
  const turn=gameState.turn==='white'?'White':'Black';
  el.textContent=turn+"'s turn";
  el.style.color=gameState.turn===myColor?'var(--green)':'var(--text2)';
}

// ======== GAME ACTIONS ========
function resignGame(){
  const div=document.createElement('div');div.className='draw-dialog';
  div.style.cssText='position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);background:#272522;padding:28px;border-radius:12px;z-index:1500;box-shadow:0 8px 32px rgba(0,0,0,0.5);text-align:center;';
  div.innerHTML=`<h3 style="margin-bottom:6px;font-size:16px;">Resign?</h3><p style="color:#b0b0b0;margin-bottom:14px;">Are you sure you want to resign?</p><div style="display:flex;gap:10px;justify-content:center;"><button class="btn btn-outline-danger" onclick="confirmResign(this)">Yes, resign</button><button class="btn btn-secondary" onclick="this.closest('.draw-dialog').remove()">Cancel</button></div>`;
  document.body.appendChild(div);
}
function confirmResign(btn){btn.closest('.draw-dialog')?.remove();socket.emit('resign',{game_id:currentGameId});}
function offerDraw(){if(drawOffered){showNotification('Draw already offered','info');return;}drawOffered=true;socket.emit('offer_draw',{game_id:currentGameId});showNotification('Draw offered','info');}
function requestRematch(){socket.emit('request_rematch',{game_id:currentGameId});showNotification('Requesting rematch...','info');}
function leaveGame(){closeGame();switchToView('lobby');}

function closeGame(){
  stopTimerCountdown();closeModal();
  document.getElementById('gameView').classList.remove('active');
  if(board){board.destroy();board=null;}
  if(analysisBoard){analysisBoard.destroy();analysisBoard=null;}
  currentGameId=null;myColor=null;gameState=null;gameOver=false;drawOffered=false;aiThinking=false;selectedSquare=null;isAiGame=false;
  whiteTimer=selectedTimeControl;blackTimer=selectedTimeControl;timerActiveColor=null;
}

function closeAnalysis(){
  if(analysisBoard){analysisBoard.destroy();analysisBoard=null;}
  switchToView('game');
}

function showAnalysis(){
  if(!gameState||!gameState.move_ucis||gameState.move_ucis.length===0){
    showNotification('No moves to analyze','info');return;
  }
  switchToView('analysis');
  analysisMoves=gameState.move_ucis||[];analysisIndex=analysisMoves.length;
  const cfg={pieceTheme:PIECE_SETS[currentPieceSet]||PIECE_SETS.wikipedia,position:gameState.fen,draggable:false,orientation:myColor==='black'?'black':'white',showErrors:false};
  if(analysisBoard){analysisBoard.destroy();}
  analysisBoard=Chessboard('analysisBoard',cfg);
  applyBoardTheme(currentBoardTheme);
  setTimeout(()=>analysisBoard.resize(),100);
  updateAnalysisUI();
  closeModal();
}

function updateAnalysisUI(){
  const game=new Chess();
  for(let i=0;i<analysisIndex;i++){try{game.move(uciToMove(analysisMoves[i]));}catch(e){}}
  if(analysisBoard)analysisBoard.position(game.fen());
  document.getElementById('analysisMoveNum').textContent=`Move ${analysisIndex} / ${analysisMoves.length}`;
  document.getElementById('analysisEval').textContent='?';
  const list=document.getElementById('analysisMoveList');
  list.innerHTML=analysisMoves.map((m,i)=>{
    const g=new Chess();
    for(let j=0;j<=i;j++){try{g.move(uciToMove(analysisMoves[j]));}catch(e){}}
    try{
      const result=g.move(uciToMove(m));g.undo();
      return `<span class="analysis-move${i===analysisIndex-1?' active':''}" onclick="analysisGoTo(${i+1})">${result.san||m}</span>`;
    }catch(e){return '<span class="analysis-move">'+m+'</span>';}
  }).join('');
}
function analysisGoTo(idx){analysisIndex=Math.max(0,Math.min(idx,analysisMoves.length));updateAnalysisUI();}
function analysisGoToStart(){analysisGoTo(0);}
function analysisGoBack(){analysisGoTo(analysisIndex-1);}
function analysisGoForward(){analysisGoTo(analysisIndex+1);}
function analysisGoToEnd(){analysisGoTo(analysisMoves.length);}

function downloadPGN(){
  if(!gameState||!gameState.move_ucis)return;
  let pgn='[Event "Chess Game"]\n[Site "Chess App"]\n[Date "'+new Date().toISOString().split('T')[0]+'"]\n[Round "1"]\n[White "'+(gameState.white_name||'White')+'"]\n[Black "'+(gameState.black_name||'Black')+'"]\n[Result "*"]\n\n';
  const moves=gameState.move_history||[];
  for(let i=0;i<moves.length;i++){
    if(i%2===0)pgn+=Math.floor(i/2)+1+'. ';
    pgn+=moves[i]+' ';
  }
  pgn+='*';
  const blob=new Blob([pgn],{type:'text/plain'}),a=document.createElement('a');
  a.href=URL.createObjectURL(blob);a.download='chess-game.pgn';a.click();URL.revokeObjectURL(a.href);
}

function toggleZenMode(){
  zenMode=!zenMode;
  document.body.classList.toggle('zen-mode',zenMode);
  if(board)setTimeout(()=>board.resize(),200);
  showNotification(zenMode?'Zen Mode on':'Zen Mode off','info');
}

// ======== GAME OVER MODAL ========
function showGameOver(result){
  document.getElementById('modalDetail').textContent=result||'The game has ended';
  document.getElementById('rematchBtn').classList.remove('hidden');
  document.getElementById('leaveBtn').classList.remove('hidden');
  document.getElementById('analyzeBtn').classList.remove('hidden');
  const lc=result?result.toLowerCase():'';
  if(lc.includes('wins')||lc.includes('checkmate')){
    const winner=gameState?(gameState.turn==='white'?'Black':'White'):'Opponent';
    document.getElementById('modalIcon').textContent=winner===myColor||(myColor==='white'?'White':'Black')===winner?'🎉':'😞';
    document.getElementById('modalTitle').textContent=result&&result.includes(' by ')?result.split(' by ')[0]+' wins!':'Game Over';
  }else if(lc.includes('draw')){document.getElementById('modalIcon').textContent='🤝';document.getElementById('modalTitle').textContent='Draw';}
  else if(lc.includes('disconnected')){document.getElementById('modalIcon').textContent='💻';document.getElementById('modalTitle').textContent='Opponent Disconnected';}
  else{document.getElementById('modalIcon').textContent='🏁';document.getElementById('modalTitle').textContent='Game Over';}
  document.getElementById('gameOverModal').classList.remove('hidden');
}
function closeModal(){document.getElementById('gameOverModal').classList.add('hidden');}

// ======== LOBBY GAMES ========
function updateLobbyGames(games){
  const container=document.getElementById('gamesList');
  if(!games||games.length===0){container.innerHTML='<div class="games-empty">No open games right now</div>';return;}
  container.innerHTML=games.map(g=>`<div class="game-item" onclick="joinByCode('${g.id}')"><div class="game-item-info"><div class="game-item-creator">${g.white||'Player'}</div><div class="game-item-status">${g.players}/2 players</div></div><button class="btn btn-sm btn-primary">Join</button></div>`).join('');
}
function joinByCode(code){document.getElementById('gameCodeInput').value=code;socket.emit('join_game',{game_id:code,elo:selectedElo,rating:myRating});}

// ======== PUZZLES ========
function getNewPuzzle(){
  const theme=document.querySelector('.theme-filter.active')?.dataset.theme||'';
  const url=theme?'/api/puzzles/random?theme='+theme:'/api/puzzles/random';
  fetch(url).then(r=>r.json()).then(d=>{
    if(d.error){showNotification(d.error,'error');return;}
    currentPuzzle=d;puzzleMoves=d.solution||[];puzzleIndex=0;puzzleSolved=false;
    document.getElementById('puzzleFeedback').textContent='';
    document.getElementById('puzzleFeedback').className='puzzle-feedback';
    const game=new Chess();game.load(d.fen);
    if(puzzleBoard){puzzleBoard.destroy();}
    const cfg={pieceTheme:PIECE_SETS[currentPieceSet]||PIECE_SETS.wikipedia,position:d.fen,draggable:false,orientation:game.turn()==='b'?'black':'white',showErrors:false};
    puzzleBoard=Chessboard('puzzleBoard',cfg);
    applyBoardTheme(currentBoardTheme);
    document.getElementById('puzzleRating').textContent='Rating: '+d.rating;
    document.getElementById('puzzleThemes').textContent='Themes: '+(d.themes||'—');
    document.getElementById('puzzleStats').textContent='Solved: '+d.solves+'/'+d.plays;
    puzzleSelectedSquare=null;
    setTimeout(()=>puzzleBoard.resize(),100);
    initPuzzleClickHandlers();
  });
}
let puzzleSelectedSquare=null;
function initPuzzleClickHandlers(){
  $(document).off('click','#puzzleBoard [data-square]');
  $(document).on('click','#puzzleBoard [data-square]',function(){
    if(puzzleSolved||!currentPuzzle||puzzleIndex>=puzzleMoves.length)return;
    const square=$(this).data('square');
    if(!puzzleSelectedSquare){puzzleSelectedSquare=square;return;}
    const expected=puzzleMoves[puzzleIndex];
    const fromSquare=expected.slice(0,2),toSquare=expected.slice(2,4);
    if(puzzleSelectedSquare===fromSquare&&square===toSquare){
      puzzleIndex++;
      const game=new Chess();game.load(currentPuzzle.fen);
      try{game.move(uciToMove(expected));}catch(e){}
      currentPuzzle.fen=game.fen();
      puzzleBoard.position(game.fen());
      if(puzzleIndex>=puzzleMoves.length){
        puzzleSolved=true;
        document.getElementById('puzzleFeedback').textContent='✓ Correct! Puzzle solved!';
        document.getElementById('puzzleFeedback').className='puzzle-feedback correct';
        fetch('/api/puzzles/'+currentPuzzle.id+'/result',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({solved:true})});
        loadPuzzleStats();
      }else{
        document.getElementById('puzzleFeedback').textContent='✓ Correct! Keep going...';
        document.getElementById('puzzleFeedback').className='puzzle-feedback correct';
        setTimeout(()=>{document.getElementById('puzzleFeedback').textContent='';document.getElementById('puzzleFeedback').className='puzzle-feedback';},800);
      }
    }else{
      document.getElementById('puzzleFeedback').textContent='✗ Wrong move! Try again.';
      document.getElementById('puzzleFeedback').className='puzzle-feedback wrong';
      playSound('error');
      puzzleBoard.position(currentPuzzle.fen);
    }
    puzzleSelectedSquare=null;
  });
}

function puzzleShowHint(){
  if(!currentPuzzle||puzzleIndex>=puzzleMoves.length)return;
  const expected=puzzleMoves[puzzleIndex];
  const toSquare=expected.slice(2,4);
  showNotification('Hint: Look at square '+toSquare.toUpperCase(),'info');
}
function puzzleShowSolution(){
  if(!currentPuzzle)return;
  showNotification('Solution: '+puzzleMoves.join(', '),'info');
}
document.addEventListener('click',function(e){
  const target=e.target.closest('.theme-filter');
  if(target){
    document.querySelectorAll('.theme-filter').forEach(t=>t.classList.remove('active'));
    target.classList.add('active');
    getNewPuzzle();
  }
});

function loadPuzzleStats(){
  fetch('/api/profile/'+document.getElementById('usernameDisplay').textContent).then(r=>r.json()).then(d=>{
    document.getElementById('puzzleRatingDisplay').textContent=d.puzzle_rating;
    document.getElementById('puzzlesSolvedDisplay').textContent=d.puzzles_solved;
  }).catch(()=>{});
}

// ======== FRIENDS ========
function showFriendSearch(){document.getElementById('friendSearchModal').classList.remove('hidden');document.getElementById('friendSearchResults').innerHTML='<div class="games-empty">Type to search...</div>';}
function closeFriendSearch(){document.getElementById('friendSearchModal').classList.add('hidden');}
let friendSearchTimeout=null;
function searchFriends(){
  const input=document.getElementById('friendSearchInput');
  const q=input.value.trim();
  if(friendSearchTimeout)clearTimeout(friendSearchTimeout);
  friendSearchTimeout=setTimeout(()=>{
    if(q.length<2){document.getElementById('friendSearchResults').innerHTML='<div class="games-empty">Type at least 2 characters</div>';return;}
    fetch('/api/friends/search?q='+encodeURIComponent(q)).then(r=>r.json()).then(users=>{
      const el=document.getElementById('friendSearchResults');
      if(!users||users.length===0){el.innerHTML='<div class="games-empty">No users found</div>';return;}
      el.innerHTML=users.map(u=>`<div class="friend-result-item"><span>${u.username} (${u.rating})</span><button class="btn btn-sm btn-play" onclick="addFriend(${u.id},'${u.username}')">Add</button></div>`).join('');
    });
  },300);
}
function addFriend(id,name){
  fetch('/api/friends/add',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({user_id:id})})
  .then(r=>r.json()).then(d=>{
    if(d.error){showNotification(d.error,'error');return;}
    showNotification(name+' added as friend!','success');
    document.getElementById('friendSearchModal').classList.add('hidden');
    loadFriends();
  });
}
function loadFriends(){
  fetch('/api/friends').then(r=>r.json()).then(friends=>{
    const el=document.getElementById('friendsList');
    if(!friends||friends.length===0){el.innerHTML='<div class="games-empty">No friends yet</div>';return;}
    el.innerHTML=friends.map(f=>`<div class="game-item" onclick="showProfile('${f.username}')"><span>${f.username}</span><span style="color:var(--green)">${f.rating}</span></div>`).join('');
  });
}

// ======== LEADERBOARD ========
function loadLeaderboard(){
  fetch('/api/leaderboard').then(r=>r.json()).then(users=>{
    const el=document.getElementById('leaderboardBody');
    if(!users||users.length===0){el.innerHTML='<tr><td colspan="7" style="color:var(--text3);text-align:center;padding:20px;">No players yet</td></tr>';return;}
    el.innerHTML=users.map((u,i)=>`<tr onclick="showProfile('${u.username}')" style="cursor:pointer">
      <td><span class="rank-num">${i+1}</span></td>
      <td><strong>${u.username}</strong></td>
      <td>${u.rating}</td>
      <td>${u.wins}</td>
      <td>${u.losses}</td>
      <td>${u.draws}</td>
      <td>${u.win_rate}%</td>
    </tr>`).join('');
  });
}

// ======== GAME ARCHIVE & REPLAY ========
function showGameArchive(username){
  const u=username||document.getElementById('usernameDisplay').textContent;
  switchToView('archive');
  fetch('/api/games/'+encodeURIComponent(u)).then(r=>r.json()).then(games=>{
    const el=document.getElementById('archiveList');
    if(!games||games.length===0){el.innerHTML='<div class="games-empty">No games found</div>';return;}
    el.innerHTML=games.map(g=>`<div class="recent-game-item" onclick="openGameReplay('${g.game_id}')">
      <span>${g.white} vs ${g.black}</span>
      <span style="color:var(--text3)">${g.result||'*'}</span>
      <span style="color:var(--text3);font-size:11px">${g.date?new Date(g.date).toLocaleDateString():''}</span>
    </div>`).join('');
  });
}

function openGameReplay(gameId){
  fetch('/api/game/'+gameId).then(r=>r.json()).then(g=>{
    if(g.error){showNotification(g.error,'error');return;}
    document.getElementById('replayModal').classList.remove('hidden');
    document.getElementById('replayTitle').textContent=g.white+' vs '+g.black;
    document.getElementById('replayResult').textContent=g.result||'';
    replayMoves=g.moves||[];replayIndex=0;
    if(replayBoard){replayBoard.destroy();}
    const cfg={pieceTheme:PIECE_SETS[currentPieceSet]||PIECE_SETS.wikipedia,position:'start',draggable:false,orientation:'white',showErrors:false};
    replayBoard=Chessboard('replayBoard',cfg);
    applyBoardTheme(currentBoardTheme);
    updateReplayUI();
    setTimeout(()=>replayBoard.resize(),200);
  });
}
function closeReplayModal(){document.getElementById('replayModal').classList.add('hidden');if(replayBoard){replayBoard.destroy();replayBoard=null;}}
function updateReplayUI(){
  const game=new Chess();
  for(let i=0;i<replayIndex;i++){try{game.move(uciToMove(replayMoves[i]));}catch(e){}}
  if(replayBoard)replayBoard.position(game.fen());
  document.getElementById('replayMoveNum').textContent=replayIndex+' / '+replayMoves.length;
  const el=document.getElementById('replayMoves');
  el.innerHTML=replayMoves.map((m,i)=>{
    const g=new Chess();
    for(let j=0;j<=i;j++){try{g.move(uciToMove(replayMoves[j]));}catch(e){}}
    try{
      const result=g.move(uciToMove(m));g.undo();
      return `<span class="analysis-move${i===replayIndex-1?' active':''}" onclick="replayGoTo(${i+1})">${result.san||m}</span>`;
    }catch(e){return '<span class="analysis-move">'+m+'</span>';}
  }).join('');
}
function replayGoTo(idx){replayIndex=Math.max(0,Math.min(idx,replayMoves.length));updateReplayUI();}
function replayGoToStart(){replayGoTo(0);}
function replayGoBack(){replayGoTo(replayIndex-1);}
function replayGoForward(){replayGoTo(replayIndex+1);}
function replayGoToEnd(){replayGoTo(replayMoves.length);}

// ======== NOTIFICATIONS ========
function showNotification(message,type){
  const container=document.getElementById('notificationContainer');
  const el=document.createElement('div');
  el.className='notif '+(type||'info');
  el.textContent=message;
  container.appendChild(el);
  setTimeout(()=>{el.classList.add('fade-out');setTimeout(()=>el.remove(),300);},2800);
}

// ======== KEYBOARD SHORTCUTS ========
document.addEventListener('keydown',e=>{
  if(e.key==='Escape'){document.querySelector('.draw-dialog')?.remove();closeModal();closeAuthModal();closeSettings();closeFriendSearch();closeReplayModal();}
  if(e.key==='ArrowLeft'&&document.getElementById('analysisView').classList.contains('active'))analysisGoBack();
  if(e.key==='ArrowRight'&&document.getElementById('analysisView').classList.contains('active'))analysisGoForward();
});

// ======== LOAD USER STATS ========
function loadUserStats(){
  const username=document.getElementById('usernameDisplay').textContent;
  if(!username||username==='Guest')return;
  fetch('/api/profile/'+encodeURIComponent(username)).then(r=>r.json()).then(d=>{
    if(d.error)return;
    document.getElementById('lobbyWins').textContent=d.wins;
    document.getElementById('lobbyLosses').textContent=d.losses;
    document.getElementById('lobbyDraws').textContent=d.draws;
    document.getElementById('lobbyStreak').textContent=d.streak>0?'W'+d.streak:d.streak<0?'L'+Math.abs(d.streak):'—';
    document.getElementById('lobbyPuzzleRating').textContent=d.puzzle_rating;
    myRating=d.rating;
    document.getElementById('lobbyRating').textContent=d.rating;
    document.getElementById('navbarRating').textContent=d.rating;
    if(d.board_theme){currentBoardTheme=d.board_theme;applyBoardTheme(d.board_theme);}
    if(d.piece_set){currentPieceSet=d.piece_set;}
    if(d.sound_enabled!==undefined){soundEnabled=d.sound_enabled;document.getElementById('soundToggle').checked=d.sound_enabled;}
  }).catch(()=>{});
}

// ======== INIT ========
selectElo('intermediate');
selectAiDifficulty('intermediate');
loadFriends();

fetch('/api/profile/'+document.getElementById('usernameDisplay').textContent).then(r=>r.json()).then(d=>{
  if(!d.error){
    myRating=d.rating;
    if(d.board_theme){currentBoardTheme=d.board_theme;applyBoardTheme(d.board_theme);}
    if(d.piece_set)currentPieceSet=d.piece_set;
    if(d.sound_enabled!==undefined)document.getElementById('soundToggle').checked=d.sound_enabled;
    loadUserStats();
  }
}).catch(()=>{});
