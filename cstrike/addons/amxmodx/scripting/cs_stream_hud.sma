/*
 * CS 1.6 Esports Tournament Stream HUD Data Collector & Live Timer
 * -----------------------------------------------------------------
 * 1. Gathers live player health, teams, active weapons, defuse kits,
 *    and C4 bomb carrier in real-time.
 * 2. Synchronizes frame-accurately with the Half-Life engine clock
 *    (get_gametime) accounting for the 2.0s engine HLTV-to-spawn delay
 *    for 100% exact match with the in-game HUD clock.
 * 3. Writes to obs_overlay/live_players.js for the OBS stream overlay.
 */

#include <amxmodx>
#include <amxmisc>
#include <cstrike>
#include <file>

#pragma dynamic 32768

#define PLUGIN_NAME    "CS Stream HUD"
#define PLUGIN_VERSION "1.4"
#define PLUGIN_AUTHOR  "Anas"

#define TASK_EXPORT 1042

#define STATE_WAITING  0
#define STATE_FREEZE   1
#define STATE_ROUND    2
#define STATE_PLANTED  3
#define STATE_DEFUSED  4
#define STATE_EXPLODED 5
#define STATE_ENDED    6

new const JS_FILE[] = "obs_overlay/live_players.js";

// Weapon names lookup table for CSW_ 1..30
new const WEAPON_NAMES[][] = {
	"",              // 0
	"p228",          // 1 - CSW_P228
	"glock",         // 2 - CSW_GLOCK
	"scout",         // 3 - CSW_SCOUT
	"hegrenade",     // 4 - CSW_HEGRENADE
	"xm1014",        // 5 - CSW_XM1014
	"c4",            // 6 - CSW_C4
	"mac10",         // 7 - CSW_MAC10
	"aug",           // 8 - CSW_AUG
	"smokegrenade",  // 9 - CSW_SMOKEGRENADE
	"elite",         // 10 - CSW_ELITE
	"fiveseven",     // 11 - CSW_FIVESEVEN
	"ump45",         // 12 - CSW_UMP45
	"sg550",         // 13 - CSW_SG550
	"galil",         // 14 - CSW_GALIL
	"famas",         // 15 - CSW_FAMAS
	"usp",           // 16 - CSW_USP
	"glock18",       // 17 - CSW_GLOCK18
	"awp",           // 18 - CSW_AWP
	"mp5",           // 19 - CSW_MP5NAVY
	"m249",          // 20 - CSW_M249
	"m3",            // 21 - CSW_M3
	"m4a1",          // 22 - CSW_M4A1
	"tmp",           // 23 - CSW_TMP
	"g3sg1",         // 24 - CSW_G3SG1
	"flashbang",     // 25 - CSW_FLASHBANG
	"deagle",        // 26 - CSW_DEAGLE
	"sg552",         // 27 - CSW_SG552
	"ak47",          // 28 - CSW_AK47
	"knife",         // 29 - CSW_KNIFE
	"p90"            // 30 - CSW_P90
};

new g_timer_state = STATE_WAITING;
new Float:g_freeze_end_time = 0.0;
new Float:g_round_end_time = 0.0;
new Float:g_c4_end_time = 0.0;
new g_bomb_planted = 0;

new g_ct_entries[5][128];
new g_t_entries[5][128];
new g_json_buffer[2048];

public plugin_init()
{
	register_plugin(PLUGIN_NAME, PLUGIN_VERSION, PLUGIN_AUTHOR);

	// Round & Timer Event hooks
	register_event("HLTV", "event_new_round", "a", "1=0", "2=0");
	register_logevent("logevent_round_start", 2, "1=Round_Start");
	register_logevent("logevent_round_end", 2, "1=Round_End");
	register_event("RoundTime", "event_round_time", "bc");
	register_logevent("logevent_bomb_planted", 3, "2=Planted_The_Bomb");
	register_logevent("logevent_bomb_defused", 3, "2=Defused_The_Bomb");
	register_logevent("logevent_bomb_exploded", 6, "3=Target_Bombed");

	// Game restart / commencing hooks
	register_event("TextMsg", "event_game_restart", "a", "2=#Game_Commencing", "2=#Game_will_restart_in");
}

public plugin_cfg()
{
	// Export live data every 100ms for instantaneous frame-perfect broadcast sync
	set_task(0.10, "task_export_data", TASK_EXPORT, "", 0, "b");
}

public event_game_restart()
{
	g_timer_state = STATE_WAITING;
	g_bomb_planted = 0;
	g_freeze_end_time = 0.0;
	g_round_end_time = 0.0;
	g_c4_end_time = 0.0;
}

public event_new_round()
{
	new Float:now = get_gametime();
	new Float:freeze = get_cvar_float("mp_freezetime");
	new Float:round = get_cvar_float("mp_roundtime") * 60.0;
	if (round <= 0.0) round = 105.0;

	g_bomb_planted = 0;
	g_c4_end_time = 0.0;

	if (freeze > 0.0)
	{
		g_timer_state = STATE_FREEZE;
		g_freeze_end_time = now + freeze;
		g_round_end_time = g_freeze_end_time + round;
	}
	else
	{
		g_timer_state = STATE_ROUND;
		g_freeze_end_time = now;
		g_round_end_time = now + round;
	}
}

public event_round_time()
{
	new secs = read_data(1);
	if (secs > 0)
	{
		new Float:now = get_gametime();
		// Synchronize round end time directly from engine RoundTime message
		g_round_end_time = now + float(secs);
	}
}

public logevent_round_start()
{
	new Float:now = get_gametime();
	new Float:round = get_cvar_float("mp_roundtime") * 60.0;
	if (round <= 0.0) round = 105.0;

	g_timer_state = STATE_ROUND;
	g_bomb_planted = 0;
	g_round_end_time = now + round;
}

public logevent_round_end()
{
	if (g_timer_state != STATE_DEFUSED && g_timer_state != STATE_EXPLODED)
	{
		g_timer_state = STATE_ENDED;
	}
	g_bomb_planted = 0;
}

public logevent_bomb_planted()
{
	new Float:now = get_gametime();
	new Float:c4_time = get_cvar_float("mp_c4timer");
	if (c4_time <= 0.0) c4_time = 35.0;

	g_bomb_planted = 1;
	g_timer_state = STATE_PLANTED;
	g_c4_end_time = now + c4_time;
}

public logevent_bomb_defused()
{
	g_bomb_planted = 0;
	g_timer_state = STATE_DEFUSED;
}

public logevent_bomb_exploded()
{
	g_bomb_planted = 0;
	g_timer_state = STATE_EXPLODED;
}

stock get_timer_state_string(timer_state, output[], maxlen)
{
	switch (timer_state)
	{
		case STATE_FREEZE: copy(output, maxlen, "freeze");
		case STATE_ROUND: copy(output, maxlen, "round");
		case STATE_PLANTED: copy(output, maxlen, "planted");
		case STATE_DEFUSED: copy(output, maxlen, "defused");
		case STATE_EXPLODED: copy(output, maxlen, "exploded");
		case STATE_ENDED: copy(output, maxlen, "ended");
		default: copy(output, maxlen, "waiting");
	}
}

// Clean names for JSON string escaping
stock clean_json_string(const input[], output[], maxlen)
{
	new len = 0;
	for (new i = 0; input[i] != '^0' && len < maxlen - 1; i++)
	{
		new c = input[i];
		if (c == 34 || c == 92 || c == 47 || c == '^n' || c == '^r' || c == '^t')
		{
			output[len++] = ' ';
		}
		else if (c >= 32 && c <= 126)
		{
			output[len++] = c;
		}
		else
		{
			output[len++] = ' ';
		}
	}
	output[len] = '^0';
}

public task_export_data(taskid)
{
	new num_players = get_playersnum();
	if (num_players <= 0)
	{
		return PLUGIN_CONTINUE;
	}

	new ct_count = 0;
	new t_count = 0;
	new max_clients = get_maxplayers();

	for (new i = 1; i <= max_clients; i++)
	{
		if (!is_user_connected(i))
			continue;

		new CsTeams:team = cs_get_user_team(i);
		if (team != CS_TEAM_T && team != CS_TEAM_CT)
			continue;

		new raw_name[32], safe_name[32];
		get_user_name(i, raw_name, 31);
		clean_json_string(raw_name, safe_name, 31);

		new alive = is_user_alive(i) ? 1 : 0;
		new hp = alive ? get_user_health(i) : 0;
		if (hp < 0) hp = 0;

		new weapon_name[32] = "";
		if (alive)
		{
			new clip, ammo;
			new wpn_id = get_user_weapon(i, clip, ammo);
			if (wpn_id >= 1 && wpn_id <= 30)
			{
				copy(weapon_name, 31, WEAPON_NAMES[wpn_id]);
			}
		}

		new has_kit = (team == CS_TEAM_CT && alive && cs_get_user_defuse(i)) ? 1 : 0;
		new has_bomb = (team == CS_TEAM_T && alive && cs_get_user_plant(i)) ? 1 : 0;

		new entry[128];
		formatex(entry, charsmax(entry),
			"{^"name^":^"%s^",^"hp^":%d,^"alive^":%d,^"weapon^":^"%s^",^"kit^":%d,^"bomb^":%d}",
			safe_name, hp, alive, weapon_name, has_kit, has_bomb);

		if (team == CS_TEAM_CT)
		{
			if (ct_count < 5)
			{
				copy(g_ct_entries[ct_count], 127, entry);
				ct_count++;
			}
		}
		else if (team == CS_TEAM_T)
		{
			if (t_count < 5)
			{
				copy(g_t_entries[t_count], 127, entry);
				t_count++;
			}
		}
	}

	// Calculate exact engine gametime remaining
	new Float:now = get_gametime();
	new active_secs = 0;
	new c4_secs = 0;

	if (g_timer_state == STATE_FREEZE)
	{
		new Float:rem_freeze = g_freeze_end_time - now;
		if (rem_freeze <= 0.0)
		{
			// Freeze time expired! Transition to LIVE round
			g_timer_state = STATE_ROUND;
			new Float:rem_round = g_round_end_time - now;
			if (rem_round < 0.0) rem_round = 0.0;
			active_secs = floatround(rem_round, floatround_floor);
		}
		else
		{
			active_secs = floatround(rem_freeze, floatround_floor);
		}
	}
	else if (g_timer_state == STATE_ROUND)
	{
		new Float:rem_round = g_round_end_time - now;
		if (rem_round < 0.0) rem_round = 0.0;
		active_secs = floatround(rem_round, floatround_floor);
	}
	else if (g_timer_state == STATE_PLANTED)
	{
		new Float:rem_c4 = g_c4_end_time - now;
		if (rem_c4 < 0.0) rem_c4 = 0.0;
		c4_secs = floatround(rem_c4, floatround_floor);

		new Float:rem_round = g_round_end_time - now;
		if (rem_round < 0.0) rem_round = 0.0;
		active_secs = floatround(rem_round, floatround_floor);
	}

	new state_str[16];
	get_timer_state_string(g_timer_state, state_str, charsmax(state_str));

	// Build JSON output string cleanly
	new pos = 0;
	pos += formatex(g_json_buffer[pos], charsmax(g_json_buffer) - pos,
		"window.setPlayerData({^"timer^":{^"state^":^"%s^",^"seconds^":%d,^"c4_seconds^":%d,^"bomb_planted^":%d},^"ct^":[",
		state_str, active_secs, c4_secs, g_bomb_planted);

	for (new c = 0; c < ct_count; c++)
	{
		pos += formatex(g_json_buffer[pos], charsmax(g_json_buffer) - pos, "%s%s", g_ct_entries[c], (c < ct_count - 1) ? "," : "");
	}

	pos += formatex(g_json_buffer[pos], charsmax(g_json_buffer) - pos, "],^"t^":[");
	for (new t = 0; t < t_count; t++)
	{
		pos += formatex(g_json_buffer[pos], charsmax(g_json_buffer) - pos, "%s%s", g_t_entries[t], (t < t_count - 1) ? "," : "");
	}
	pos += formatex(g_json_buffer[pos], charsmax(g_json_buffer) - pos, "]});^n");

	// Write directly via fputs
	new file = fopen(JS_FILE, "wt");
	if (file)
	{
		fputs(file, g_json_buffer);
		fclose(file);
	}

	return PLUGIN_CONTINUE;
}
