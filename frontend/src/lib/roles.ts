/* Roles that take calls.

   Mirrors CALLING_ROLES / is_calling_rm() in backend/app/core/auth.py — keep the two
   in step. `test_rm` is an RM used for dry runs: dialled by campaigns and badged TEST
   in the picker, but never assigned a WhatsApp conversation.

   Gates are written "is this person an RM?" and the else-branch is admin, so a calling
   role missed at a call site doesn't lose a feature — it changes which side of an
   access check the user lands on. One predicate, used everywhere. */
export const CALLING_ROLES = ["rm", "test_rm"];

export const isCallingRm = (role?: string | null) => !!role && CALLING_ROLES.includes(role);
