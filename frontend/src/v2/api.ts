/**
 * V2 API-klient · parallell migration.
 *
 * Wrappar /v2/*-endpoints. Använder samma token från `@/api/client`
 * så ingen separat auth behövs.
 */
import { api } from "@/api/client";

export type SpendProfile = "sparsam" | "balanserad" | "slosa";
export type FairnessChoice = "50_50" | "proportionellt" | "pool";
export type PartnerModel = "solo" | "ai" | "klasskompis";

export type V2Status = {
  role: "student" | "teacher" | "demo";
  v2_eligible: boolean;
  v2_onboarding_completed: boolean;
  v2_level: number;
  v2_spend_profile: SpendProfile;
  v2_fairness_choice: FairnessChoice | null;
  v2_partner_model: PartnerModel;
  is_super_admin: boolean;
};

export type OnboardingComplete = {
  student_id: number;
  completed_at: string;
  v2_level: number;
  redirect_to: string;
};

export type V2RosterRow = {
  student_id: number;
  display_name: string;
  class_label: string | null;
  v2_enabled: boolean;
  v2_onboarding_completed: boolean;
  v2_level: number;
};

export const v2Api = {
  status: () => api<V2Status>("/v2/status"),
  completeOnboarding: (body: {
    spend_profile: SpendProfile;
    fairness_choice: FairnessChoice | null;
    partner_model: PartnerModel;
  }) =>
    api<OnboardingComplete>("/v2/onboarding/complete", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  // Lärar-API:er för att toggla v2 per elev
  toggleStudent: (studentId: number, enabled: boolean) =>
    api<{ student_id: number; v2_enabled: boolean; display_name: string }>(
      `/v2/teacher/students/${studentId}/v2-toggle`,
      { method: "POST", body: JSON.stringify({ enabled }) },
    ),
  bulkToggle: (enabled: boolean, studentIds?: number[]) =>
    api<{ affected: number; enabled: boolean }>(
      "/v2/teacher/students/v2-bulk",
      {
        method: "POST",
        body: JSON.stringify({
          enabled,
          student_ids: studentIds ?? null,
        }),
      },
    ),
  roster: () =>
    api<V2RosterRow[]>("/v2/teacher/students/v2-roster"),
};
