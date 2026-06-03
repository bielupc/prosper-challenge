import type { Patient } from '../types'
import { formatDob } from '../utils'

interface Props {
  patients: Patient[]
}

export default function PatientsTable({ patients }: Props) {
  return (
    <div className="bg-white rounded-card shadow-card p-6">
      <h2 className="font-inter font-medium text-ink text-xl mb-5">Patients</h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-border-gray text-left">
              <th className="pb-2 font-manrope font-medium text-warm-500">Name</th>
              <th className="pb-2 font-manrope font-medium text-warm-500">Date of Birth</th>
              <th className="pb-2 font-manrope font-medium text-warm-500">Email</th>
              <th className="pb-2 font-manrope font-medium text-warm-500">Phone</th>
            </tr>
          </thead>
          <tbody>
            {patients.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-8 text-center text-warm-500 font-manrope">
                  No patients yet
                </td>
              </tr>
            ) : (
              patients.map(p => (
                <tr key={p.id} className="border-b border-border-gray last:border-0">
                  <td className="py-3 font-manrope font-medium text-ink">
                    {p.first_name} {p.last_name}
                  </td>
                  <td className="py-3 font-manrope text-warm-600">{formatDob(p.date_of_birth)}</td>
                  <td className="py-3 font-manrope text-warm-600">{p.email ?? '—'}</td>
                  <td className="py-3 font-manrope text-warm-600">{p.phone ?? '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
