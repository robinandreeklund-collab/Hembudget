/**
 * EchoButton — v2-stylad wrapper kring AskAI-komponenten.
 *
 * Lägg till på vilken v2-page som helst för att låta eleven öppna
 * Echo (Claude Sonnet) med kontext. Visar bara om läraren har
 * AI-toggle på (AskAI hanterar gating själv).
 *
 * Användning:
 *   <EchoButton context="Lönesamtal med Maria" />
 */
import { AskAI } from "../components/AskAI";

type Props = {
  context: string;
  moduleId?: number;
  stepId?: number;
};

export function EchoButton({ context, moduleId, stepId }: Props) {
  return (
    <AskAI
      moduleId={moduleId}
      stepId={stepId}
      contextLabel={context}
    />
  );
}
