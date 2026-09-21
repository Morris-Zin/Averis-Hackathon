// Pure guards for case identity; the review hook consumes these rules.
export function isActionAllowed(
  requestedId: string,
  loadedId: string | null,
): boolean {
  return Boolean(requestedId) && loadedId === requestedId;
}

export function shouldIgnoreLateResponse(
  requestedId: string,
  responseId: string,
  responseVersion: number,
  currentVersion: number,
): boolean {
  return (
    responseVersion !== currentVersion ||
    !requestedId ||
    responseId !== requestedId
  );
}

export function shouldInvalidateOnNavigate(
  previousRequestedId: string,
  nextRequestedId: string,
): boolean {
  return previousRequestedId !== nextRequestedId;
}
