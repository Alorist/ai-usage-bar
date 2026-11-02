-- AI Usage Bar: turns data\rainmeter_data.txt (written by bin\aiusage\aiusage.exe)
-- into skin variables, lays out only the sections this PC has (Claude / Codex /
-- tokens), and builds the hover tooltips. Runs every skin update (30 s) and right
-- after each data fetch via Refresh().

local ACC   = { CL = '224,138,94,255', CX = '138,180,248,255' }
local AMBER = '245,185,74,255'
local RED   = '255,107,107,255'
local WHITE = '255,255,255,240'
local FAINT = '255,255,255,105'
local TRACK = '255,255,255,38'
local NONE  = '0,0,0,0'
local SEC_W = { CL = 338, CX = 334 }    -- section widths (must match tools/gen_skins.py)
local BAR_W, BAR_MIN = 56, 6

local D, dataFile, lastRead, shown, variant = {}, '', -1000, '', ''

function Initialize()
  dataFile = SKIN:GetVariable('DataFile')
  variant = SKIN:GetVariable('Variant', 'Taskbar')
end

local function read()
  local f = io.open(dataFile, 'r')
  if not f then return end
  local t = {}
  for line in f:lines() do
    local k, v = line:match('^([%w_]+)=(.*)$')
    if k then t[k] = v end
  end
  f:close()
  D = t
end

local function num(k) return tonumber(D[k]) or 0 end
local function str(k) return D[k] or '' end
local function set(k, v) SKIN:Bang('!SetVariable', k, tostring(v)) end

local function ago(ts, now)
  local s = math.max(0, now - ts)
  if s < 90 then return 'just now' end
  if s < 3600 then return math.floor(s / 60) .. 'm ago' end
  if s < 86400 then return math.floor(s / 3600) .. 'h ago' end
  return math.floor(s / 86400) .. 'd ago'
end

local function resetText(ts, now)
  local s = math.floor(ts - now)
  if s <= 0 then return 'resetting now' end
  if s < 3600 then return string.format('resets in %dm', math.max(1, math.floor(s / 60))) end
  if s < 86400 then return string.format('resets in %dh %02dm', math.floor(s / 3600), math.floor(s % 3600 / 60)) end
  return 'resets ' .. os.date('%a %H:%M', ts)
end

local function fmtTokens(n)
  if n >= 1e9 then return string.format('%.1fB', n / 1e9) end
  if n >= 1e6 then return string.format('%.1fM', n / 1e6) end
  if n >= 1e3 then return string.format('%.1fK', n / 1e3) end
  return tostring(math.floor(n))
end

local function money(x)
  local s = string.format('%.2f', x)
  local int, frac = s:match('^(%d+)%.(%d+)$')
  if not int then return '$' .. s end
  int = int:reverse():gsub('(%d%d%d)', '%1,'):reverse():gsub('^,', '')
  return '$' .. int .. '.' .. frac
end

local function moneyShort(x)
  if x < 100 then return string.format('$%.2f', x) end
  return (money(math.floor(x + 0.5)):gsub('%.00$', ''))
end

local function service(key, p, now)
  local err, seen = str(key .. '_error'), num(key .. '_seen_at')
  local status = 'live'
  if err ~= '' then
    status = seen > 0 and ('offline - data from ' .. ago(seen, now)) or ('offline - ' .. err)
  elseif seen == 0 then
    status = 'waiting for data'
  elseif key == 'codex' then
    status = 'last used ' .. ago(seen, now)
  end
  set(p .. 'Dot', err ~= '' and AMBER or ACC[p])
  local plan = str(key .. '_plan')
  local tip = { (key == 'claude' and 'Claude' or 'Codex') .. (plan ~= '' and (' ' .. plan) or '') .. '  -  ' .. status }

  local n = num(key .. '_n')
  for i = 1, math.max(2, n) do
    local q = key .. '_' .. i .. '_'
    local pct, right = 0, ''
    if i <= n then
      pct = math.max(0, math.min(100, num(q .. 'pct')))
      local r, note = num(q .. 'reset'), str(q .. 'note')
      if r > now then
        right = resetText(r, now)
      else
        if r > 0 or note ~= '' then pct = 0 end      -- window rolled over since last look
        right = (note ~= '' and note) or (r > 0 and 'reset since last update') or ''
      end
      tip[#tip + 1] = string.format('%s: %d%%   %s', str(q .. 'label'), math.floor(pct + 0.5), right)
    end
    if i <= 2 then                                    -- the bar shows the first two windows
      local col = (pct >= 90 and RED) or (pct >= 70 and AMBER) or ACC[p]
      set(p .. 'Pct' .. i, i <= n and string.format('%d%%', math.floor(pct + 0.5)) or '-')
      set(p .. 'PctColor' .. i, pct >= 70 and col or WHITE)
      set(p .. 'W' .. i, pct > 0 and math.max(BAR_MIN, math.floor(BAR_W * pct / 100)) or BAR_MIN)
      set(p .. 'Fill' .. i, pct > 0 and col or NONE)
    end
  end
  set(p .. 'Tip', table.concat(tip, '\n'))
end

local function tokens(now)
  local err, seen = str('tok_error'), num('tok_seen_at')
  set('TodayShort', moneyShort(num('tok_today_cost')))
  set('WeekShort', moneyShort(num('tok_week_cost')))
  local head = 'Token usage (API-equivalent value)'
  if err ~= '' then
    head = head .. '  -  offline' .. (seen > 0 and (', data from ' .. ago(seen, now)) or (': ' .. err))
  end
  local tip = { head }
  for i = 1, 7 do
    local name = str('day_' .. i .. '_name')
    if name ~= '' then tip[#tip + 1] = string.format('%-6s %s', name, money(num('day_' .. i .. '_cost'))) end
  end
  tip[#tip + 1] = 'Today ' .. fmtTokens(num('tok_today_tokens')) .. ' tokens, 7 days ' .. fmtTokens(num('tok_week_tokens'))
  set('TokTip', table.concat(tip, '\n'))
end

-- Show only the sections this PC has, packed left to right with dividers between them.
local function layout()
  local cl = D['claude_available'] ~= '0'
  local cx = D['codex_available'] == '1'
  local tk = D['tok_available'] == '1'
  if not (cl or cx or tk) then cl = true end         -- nothing found: keep Claude visible with "-"
  local key = (cl and 'C' or '') .. (cx and 'X' or '') .. (tk and 'T' or '')
  if key == shown then return end
  shown = key

  local secs = {}
  if cl then secs[#secs + 1] = 'CL' end
  if cx then secs[#secs + 1] = 'CX' end
  if tk then secs[#secs + 1] = 'TK' end
  local x = 18
  for i, s in ipairs(secs) do
    set(s .. 'X', x)
    if s ~= 'TK' then
      set('BgW', x + SEC_W[s] + 4)                   -- used when there is no tokens section
      if i < #secs then set('Div' .. i .. 'X', x + SEC_W[s]); x = x + SEC_W[s] + 18 end
    end
  end
  set('TKOn', tk and 1 or 0)
  SKIN:Bang(cl and '!ShowMeterGroup' or '!HideMeterGroup', 'Claude')
  SKIN:Bang(cx and '!ShowMeterGroup' or '!HideMeterGroup', 'Codex')
  SKIN:Bang(tk and '!ShowMeterGroup' or '!HideMeterGroup', 'Tokens')
  SKIN:Bang(#secs >= 2 and '!ShowMeterGroup' or '!HideMeterGroup', 'Div1')
  SKIN:Bang(#secs >= 3 and '!ShowMeterGroup' or '!HideMeterGroup', 'Div2')
end

-- The Mini variant centres itself at the top of the main screen (the taskbar
-- variant is placed by the helper program instead).
local function placeMini()
  if variant ~= 'Mini' then return end
  local bg = SKIN:GetMeter('Bg')
  if not bg then return end
  local w = bg:GetW()
  local sx = tonumber(SKIN:GetVariable('SCREENAREAX')) or 0
  local sy = tonumber(SKIN:GetVariable('SCREENAREAY')) or 0
  local sw = tonumber(SKIN:GetVariable('SCREENAREAWIDTH')) or 1920
  local x, y = math.floor(sx + (sw - w) / 2), sy + 14
  local cx, cy = tonumber(SKIN:GetX()), tonumber(SKIN:GetY())
  if w > 0 and (cx ~= x or cy ~= y) then SKIN:Bang('!Move', x, y) end
end

function Update()
  local now = os.time()
  if now - lastRead >= 20 then read(); lastRead = now end
  local up = num('updated_at')
  set('UpdatedColor', (up > 0 and now - up > 900) and AMBER or FAINT)   -- data older than 15 min
  layout()
  service('claude', 'CL', now)
  service('codex', 'CX', now)
  tokens(now)
  placeMini()
  return 0
end

-- called when the data fetch finishes: re-read the data now
function Refresh() lastRead = -1000; Update() end
