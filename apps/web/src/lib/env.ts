import { z } from "zod";

const envSchema = z.object({
  apiUrl: z.string().url(),
  useMocks: z.boolean(),
});

// NEXT_PUBLIC_* vars must be referenced statically so Next can inline them.
export const env = envSchema.parse({
  apiUrl: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  useMocks: (process.env.NEXT_PUBLIC_USE_MOCKS ?? "true") !== "false",
});
