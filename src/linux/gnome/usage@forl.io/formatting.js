/*
 * The words the panel uses, as src/common/ui/formatting.py writes them.
 *
 * A window is described by when it resets, as a wall clock time rather than a
 * duration, and the day is named only when the reset is not today, which is how
 * Claude's own usage view reads. The words are English, as they are in the
 * panel, so the day is named from a list rather than from the locale.
 */

import GLib from 'gi://GLib';

const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

// Return a usage percentage as a whole number followed by a percent sign.
export function formatPercent(percent) {
	return `${Math.round(percent)}%`;
}

// Return an ISO 8601 moment in local time, rounded to the nearest minute, or
// null when there is none. Reset times arrive one second short of the hour, so
// rounding is what turns 11:59:59 PM into the 12:00 AM a reader expects.
function localMinute(iso) {
	if (!iso) {
		return null;
	}
	const moment = GLib.DateTime.new_from_iso8601(iso, null);
	if (moment === null) {
		return null;
	}
	const local = moment.to_local();
	const rounded = local.add_seconds(-local.get_seconds());
	return local.get_second() >= 30 ? rounded.add_minutes(1) : rounded;
}

// Return the wall clock time of a local moment, on a twelve hour clock.
function formatClock(local) {
	const hour = local.get_hour();
	return `${hour % 12 || 12}:${String(local.get_minute()).padStart(2, '0')} ${hour < 12 ? 'AM' : 'PM'}`;
}

// Return a sentence saying when a window resets, such as "Resets at 2:00 PM" or
// "Resets Sunday 12:00 AM", and an empty string when there is no reset time.
export function formatResetAt(iso) {
	const local = localMinute(iso);
	if (local === null) {
		return '';
	}
	const today = GLib.DateTime.new_now_local();
	if (local.get_year() === today.get_year() && local.get_day_of_year() === today.get_day_of_year()) {
		return `Resets at ${formatClock(local)}`;
	}
	return `Resets ${WEEKDAYS[local.get_day_of_week() - 1]} ${formatClock(local)}`;
}

// Return the second line under a window name: the reset sentence, preceded on
// its own line for a per model window by what that limit covers.
export function formatSubtitle(usage) {
	const reset = formatResetAt(usage.resets_at);
	if (!usage.scope) {
		return reset;
	}
	const scope = `Separate weekly limit for ${usage.scope}`;
	return reset ? `${scope}\n${reset}` : scope;
}

// Return the line saying how long until the next reading.
export function formatNextUpdate(seconds) {
	return `Next update in ${Math.max(0, Math.floor(seconds))}s`;
}
