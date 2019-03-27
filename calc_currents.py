# This code was tested using Python 3.6.4, GPAW 1.3.0, and ASE 3.16.0

# This script must be run with access to utils_zcolor.py and with an appropriately setup 'data' directory which can be generated with the make_dirs.sh shell script.
# The output is a jmol (.spt) script, and can be collected with the collect_spt.py script.

# For help contact marc@chem.ku.dk / marchamiltongarner@hotmail.com

# Please cite the appropriate work.
# s-band electrode transmission code: DOI: 10.1021/acs.jpclett.8b03432
# Current density code: Jensen et al. "When Current Does Not Follow Bonds: Current Density In Saturated Molecules" Submitted 2018
# Current density with cylindrical coordinates: Garner et al. "Helical Orbitals and Circular Currents in Linear Carbon Wires" Submitted 2018

from utils_zcolor import *
from numpy import ascontiguousarray as asc
from gpaw.lcao.tools import dump_hamiltonian_parallel, get_bfi2
from gpaw.lcao.tools import get_lcao_hamiltonian, get_lead_lcao_hamiltonian
from gpaw import GPAW, FermiDirac
from ase.io.trajectory import Trajectory
from ase.dft.kpoints import monkhorst_pack
from ase.io import read, write
from ase.units import Hartree
from ase import Atoms
import argparse
import os
from tqdm import tqdm
import numpy as np
from gpaw import setup_paths
import pickle as pickle
import matplotlib
matplotlib.use('agg')


#from ase.visualize import view


#from my_poisson_solver import solve_directly, minus_gradient, solve_with_multigrid


parser = argparse.ArgumentParser(description='Process some integers.')
parser.add_argument(
    '--path',
    default='data/',
    help='path to data folder')
parser.add_argument(
    '--xyzname',
    default='hh_junc.traj',
    help='name of the xyz or traj file')
parser.add_argument('--basis',
                    default='dzp',
                    help='basis (sz, dzp, ...)')
parser.add_argument('--ef',
                    default=0.,
                    help='fermi')
args = parser.parse_args()
path = os.path.abspath(args.path) + "/"
ef = float(args.ef)
basis = args.basis
path = os.path.abspath(args.path) + "/"
xyzname = args.xyzname

"""
Constants
"""
xc = 'PBE'
FDwidth = 0.1
kpts = (1, 1, 1)
mode = 'lcao'
h = 0.20
vacuum = 4
basis_full = {'H': 'sz',
              'C': basis,
              'S': basis,
              'N': basis,
              'Si': basis,
              'Ge': basis,
              'B': basis,
              'O': basis,
              'F': basis,
              'Cl': basis,
              'P': basis,
              'Ru': basis}

# grid_size is the divider for h
grid_size = 3

molecule = read(path + xyzname)

# Align z-axis and cutoff at these atoms, OBS paa retningen.
align1 = 2
align2 = 4

"""
Identify end atoms and align according to z-direction
atoms the furthers from one another
"""
atoms = identify_and_align(molecule, align1, align2)

symbols = atoms.get_chemical_symbols()

np.save(path + "positions.npy", atoms.get_positions())
np.save(path + "symbols.npy", symbols)
atoms.write(path + "central_region.xyz")

# Run and converge calculation
calc = GPAW(h=h,
            xc=xc,
            basis=basis_full,
            occupations=FermiDirac(width=FDwidth),
            kpts=kpts,
            mode=mode,
            symmetry={'point_group': False, 'time_reversal': False},
            charge=0)
atoms.set_calculator(calc)
atoms.get_potential_energy()  # Converge everything!
Ef = atoms.calc.get_fermi_level()

wfs = calc.wfs
kpt = monkhorst_pack((1, 1, 1))

basename = "basis_{0}__xc_{1}__h_{2}__fdwithd_{3}__kpts_{4}__mode_{5}__vacuum_{6}__".format(
    basis, xc, h, FDwidth, kpts, mode, vacuum)

dump_hamiltonian_parallel(path + 'scat_' + basename, atoms, direction='z')

a_list = range(0, len(atoms))
bfs = get_bfi2(symbols, basis_full, range(len(a_list)))
rot_mat = np.diag(v=np.ones(len(bfs)))
c_fo_xi = asc(rot_mat.real.T)  # coefficients
phi_xg = calc.wfs.basis_functions.gd.zeros(len(c_fo_xi))
wfs = calc.wfs
gd0 = calc.wfs.gd
calc.wfs.basis_functions.lcao_to_grid(c_fo_xi, phi_xg, -1)
np.save(path + basename + "ao_basis_grid", [phi_xg, gd0])
plot_basis(atoms, phi_xg, ns=len(bfs), folder_name=path + "basis/ao")
print('fermi is', Ef)

# MO - basis
H_ao, S_ao = pickle.load(open(path + 'scat_' + basename + '0.pckl', 'rb'))
H_ao = H_ao[0, 0]
S_ao = S_ao[0]

eig, vec = np.linalg.eig(np.dot(np.linalg.inv(S_ao), H_ao))
order = np.argsort(eig)
eig = eig.take(order)
vec = vec.take(order, axis=1)
S_mo = np.dot(np.dot(vec.T.conj(), S_ao), vec)
vec = vec / np.sqrt(np.diag(S_mo))
S_mo = np.dot(np.dot(vec.T.conj(), S_ao), vec)
H_mo = np.dot(np.dot(vec.T, H_ao), vec)

rot_mat = vec
c_fo_xi = asc(rot_mat.real.T)  # coefficients
mo_phi_xg = calc.wfs.basis_functions.gd.zeros(len(c_fo_xi))
wfs = calc.wfs
gd0 = calc.wfs.gd
calc.wfs.basis_functions.lcao_to_grid(c_fo_xi, mo_phi_xg, -1)
np.save(path + basename + "mo_energies", eig)
np.save(path + basename + "mo_basis", mo_phi_xg)
plot_basis(atoms, mo_phi_xg, ns=len(bfs), folder_name=path + "basis/mo")
print("ready to run transmission")


# calculate the transmission AJ style

# Variables
co = 1e-10
bias = 1e-3
gamma = 1e0
estart, eend = [-6, 6]
es = 1e-2
electrode_type = "H"
correction = False

# constants
eV2au = 1/Hartree

fname = "basis_{0}__xc_{1}__h_{2}__fdwithd_{3}__kpts_{4}__mode_{5}__vacuum_{6}__".format(
    basis, xc, h, FDwidth, kpts, mode, vacuum)

basename = "__basis_{0}__h_{1}__cutoff_{2}__xc_{3}__gridsize_{4:.2f}__bias_{5}__ef_{6}__gamma_{7}__energy_grid_{8}_{9}_{10}__muliti_grid__type__".format(
    basis, h, co, xc, grid_size, bias, ef, gamma, estart, eend, es)
plot_basename = "plots/" + basename
data_basename = "data/" + basename

bias *= eV2au
ef *= eV2au
estart *= eV2au
eend *= eV2au
es *= eV2au
gamma *= eV2au

H_ao, S_ao = pickle.load(open(path + 'scat_' + fname + '0.pckl', 'rb'))
H_ao = H_ao[0, 0] * eV2au
S_ao = S_ao[0]
n = len(H_ao)

GamL = np.zeros([n, n])
GamR = np.zeros([n, n])

GamL[0, 0] = gamma
GamR[n - 1, n - 1] = gamma

print("Calculating transmission")
energy_grid = np.arange(estart, eend, es)

Gamma_L = [GamL for en in range(len(energy_grid))]
Gamma_R = [GamR for en in range(len(energy_grid))]

Gamma_L = np.swapaxes(Gamma_L, 0, 2)
Gamma_R = np.swapaxes(Gamma_R, 0, 2)

Gr = ret_gf_ongrid(energy_grid, H_ao, S_ao, Gamma_L, Gamma_R)

trans = calc_trans(energy_grid, Gr, Gamma_L, Gamma_R)

plot_transmission(energy_grid*Hartree, trans, path + plot_basename + "trans.png")
np.save(path+data_basename+'trans_full.npy', [energy_grid*Hartree, trans])

print("transmission done")

# current parametre, dobbeltcheck hvori ef indgaar for og efter den redefineres
bias = 1e-3
ef = 0
# De genomregnes fra eV til au laengere nede
correction = False
"""
Calculate the current
"""
# fname = "basis_{0}__xc_{1}__fdwithd_{2}__kpts_{3}__mode_{4}__vacuum_{5}__".format(basis,xc,FDwidth,kpts,mode,vacuum)
fname = "basis_{0}__xc_{1}__h_{2}__fdwithd_{3}__kpts_{4}__mode_{5}__vacuum_{6}__".format(
    basis, xc, h, FDwidth, kpts, mode, vacuum)

basename = "__basis_{0}__h_{1}__cutoff_{2}__xc_{3}__gridsize_{4:.2f}__bias_{5}__ef_{6}__gamma_{7}__energy_grid_{8}_{9}_{10}__muliti_grid__type__"\
    .format(basis, h, co, xc, grid_size, bias, ef, gamma, estart, eend, es)
plot_basename = "plots/" + basename
data_basename = "data/" + basename

bias *= eV2au
ef *= eV2au

eig, vec = np.linalg.eig(np.dot(np.linalg.inv(S_ao), H_ao))
order = np.argsort(eig)
eig = eig.take(order)
vec = vec.take(order, axis=1)
S_mo = np.dot(np.dot(vec.T.conj(), S_ao), vec)
vec = vec/np.sqrt(np.diag(S_mo))
S_mo = np.dot(np.dot(vec.T.conj(), S_ao), vec)
H_mo = np.dot(np.dot(vec.T, H_ao), vec)

GamL_mo = np.dot(np.dot(vec.T, GamL), vec)
GamR_mo = np.dot(np.dot(vec.T, GamR), vec)

Gamma_L_mo = [GamL_mo for en in range(len(energy_grid))]
Gamma_R_mo = [GamR_mo for en in range(len(energy_grid))]

Gamma_L_mo = np.swapaxes(Gamma_L_mo, 0, 2)
Gamma_R_mo = np.swapaxes(Gamma_R_mo, 0, 2)

np.savetxt(path+'eig_spectrum.txt', X=eig*Hartree, fmt='%.10s', newline='\n',)
# find HOMO and LUMO
for n in range(len(eig)):
    if eig[n] < 0 and eig[n+1] > 0:
        HOMO = eig[n]
        LUMO = eig[n+1]
        midgap = (HOMO+LUMO)/2.0

        np.savetxt(path + "basis/mo/"+'homo_index.txt',
                   X=['HOMO index is ', n], fmt='%.10s', newline='\n')
        break

hl_gap = ['HOMO er ', HOMO*Hartree, 'LUMO er ', LUMO*Hartree, 'mid-gap er ', midgap*Hartree]
np.savetxt(path+'HOMO_LUMO.txt', X=hl_gap, fmt='%.10s', newline='\n')

Gr_mo = ret_gf_ongrid(energy_grid, H_mo, S_mo, Gamma_L_mo, Gamma_R_mo)
trans_mo = calc_trans(energy_grid, Gr_mo, Gamma_L_mo, Gamma_R_mo)
plot_transmission(energy_grid, trans_mo, path + plot_basename + "trans_mo.png")
np.save(path + data_basename + 'trans_full_mo.npy', [energy_grid, trans_mo])

"""Current with fermi functions"""
fR, fL = fermi_ongrid(energy_grid, ef, bias)
dE = energy_grid[1] - energy_grid[0]
current_trans = (1/(2*np.pi))*np.array([trans[en].real *
                                        (fL[en]-fR[en])*dE for en in range(len(energy_grid))]).sum()

np.save(path+data_basename+"current_trans.npy", current_trans)

Sigma_lesser = lesser_se_ongrid(energy_grid, Gamma_L, Gamma_R, fL, fR)
G_lesser = lesser_gf_ongrid(energy_grid, Gr, Sigma_lesser)
G_lesser2 = lesser_gf_ongrid2(energy_grid, Gr, Gamma_L)

#    np.save(path+data_basename+"matrices.npy",[H_ao,S_ao,Gr,G_lesser,energy_grid])

"""Current approx at low temp"""
Sigma_r = -1j/2. * (GamL + GamR)  # + V_pot

plot_complex_matrix(Sigma_r, path+"Sigma_r")

Gr_approx = retarded_gf2(H_ao, S_ao, ef, Sigma_r)

Sigma_r = 1j*np.zeros(Gamma_L.shape)
for i in range(len(energy_grid)):
    Sigma_r[:, :, i] = -1j/2. * (Gamma_L[:, :, i] + Gamma_R[:, :, i])  # + V_pot

basis = np.load(path+fname+"ao_basis_grid.npy")
Gles = Gr_approx.dot(GamL).dot(Gr_approx.T.conj())
Gles *= bias

Sigma_r_mo = -1j/2. * (GamL_mo + GamR_mo)
Gr_approx_mo = retarded_gf2(H_mo, S_mo, ef, Sigma_r_mo)
Gles_mo = Gr_approx_mo.dot(GamL_mo).dot(Gr_approx_mo.T.conj())

plot_complex_matrix(Gles, path+"Gles")

Tt = GamL.dot(Gr_approx).dot(GamR).dot(Gr_approx.T.conj())
Tt_mo = GamL_mo.dot(Gr_approx_mo).dot(GamR_mo).dot(Gr_approx_mo.T.conj())
current_dV = (bias/(2*np.pi))*Tt.trace()

np.save(path+data_basename+"matrices_dV.npy", [Gr_approx, Gles, GamL])
np.save(path+data_basename+"matrices_mo_dV.npy", [Gr_approx_mo, Gles_mo, GamL_mo])
np.save(path+data_basename+"trans_dV.npy", [ef, Tt.trace()])
np.save(path+data_basename+"trans_mo_dV.npy", [ef, Tt_mo.trace()])
np.save(path+data_basename+"current_dV.npy", current_dV)

basis_data = np.load(path+fname+"ao_basis_grid.npy")
phi_xg, gd0 = basis_data
x_cor = gd0.coords(0)
y_cor = gd0.coords(1)
z_cor = gd0.coords(2)

"""Non corrected current"""
current_c, jx_c, jy_c, jz_c, x_cor, y_cor, z_cor, gd0 = Jc_current(Gles, path, data_basename, fname)
np.save(path+data_basename+"current_c_all.npy",
        np.array([jx_c, jy_c, jz_c, x_cor, y_cor, z_cor]))
np.save(path+data_basename+"current_c.npy", np.array([current_c, x_cor, y_cor, z_cor]))

dx = (x_cor[1]-x_cor[0])
dy = (y_cor[1]-y_cor[0])
dz = (z_cor[1]-z_cor[0])

SI = 31
EI = -31
j_z_cut = jz_c[:, :, SI:EI]
multiplier = 1/(3*j_z_cut[::2, ::2, ::2].max())
cut_off = j_z_cut[::2, ::2, ::2].max()/20.

# sjette sidste arg er divider for real space grid, multiplier giver tykkere diameter
plot_current(jx_c, jy_c, jz_c, x_cor, y_cor, z_cor, path+"current",
             grid_size, multiplier, cut_off, path, align1, align2)

if correction == True:
    dx = (x_cor[1]-x_cor[0])
    dy = (y_cor[1]-y_cor[0])
    dz = (z_cor[1]-z_cor[0])
    dA = dx*dy
    divJc = div(jx_c, jy_c, jz_c, dx, dy, dz)

    divJcz = divJc.sum(axis=(0, 1))*dA
    np.save(path+data_basename+"divJcz.npy", np.array([divJcz, x_cor, y_cor, z_cor]))

    # print "Importing lowdin basis"
    """lowdin"""
    lowdin_phi_xg = np.load(path+fname+"lowdin_basis.npy")
    U = np.load(path+fname+"lowdin_U.npy")

    Sigma_r = -1j/2. * (GamL + GamR)
    divJ = get_divJ(Gr_approx, Sigma_r, GamL, GamR, U, bias, gd0, lowdin_phi_xg[0])
    divJz = divJ.sum(axis=(0, 1))*dA

    """ Solving the poisson equation"""
    rho_n = divJ - divJc
    rhoz = rho_n.sum(axis=(0, 1))*dA

    tol = 3e-12

    sol = solve_with_multigrid(rho_n.real, x_cor, y_cor, z_cor, tol)

    np.save(path+data_basename+"sol_all_{0}.npy".format(tol),
            np.array([sol, x_cor, y_cor, z_cor]))
    solz = sol.sum(axis=(0, 1))*dA

    jx2, jy2, jz2 = gradientO4(sol, dx, dy, dz)
    jz2 *= -1
    jy2 *= -1
    jx2 *= -1

    current_nl_my = jz2.sum(axis=(0, 1))*dA

    divJnl = div(jx2, jy2, jz2, dx, dy, dz)
    divJnlz = divJnl.sum(axis=(0, 1))*dA

    np.save(path + data_basename + "divJ.npy", divJ)
    np.save(path+data_basename+"rhoz.npy", np.array([rhoz, x_cor, y_cor, z_cor]))
    np.save(path+data_basename+"rho_all.npy", np.array([rho_n, x_cor, y_cor, z_cor]))
    np.save(path+data_basename+"divJz.npy", np.array([divJz, x_cor, y_cor, z_cor]))
    np.save(path+data_basename+"divJnl_{0}.npy".format(tol), np.array([divJnl]))
    np.save(path+data_basename+"divJnlz_{0}.npy".format(tol),
            np.array([divJnlz, x_cor, y_cor, z_cor]))
    np.save(path+data_basename+"current_all_{0}.npy".format(tol), np.array([jx2, jy2, jz2]))
    np.save(path+data_basename +
            "poisson_{0}__solz.npy".format(tol), np.array([solz, x_cor, y_cor, z_cor]))
    np.save(path+data_basename +
            "poisson_{0}__current_nl_my.npy".format(tol), np.array([current_nl_my, x_cor, y_cor, z_cor]))
else:
    pass