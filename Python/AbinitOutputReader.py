#!/usr/bin/python
#
# Copyright 2015 John Kendrick
#
# This file is part of PDielec
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the MIT License 
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. 
#
# You should have received a copy of the MIT License
# along with this program, if not see https://opensource.org/licenses/MIT
"""Read the Abinit output files"""
import string
import re
import numpy as np
import math 
import os, sys
from Python.Constants import *
from Python.UnitCell import *
from Python.GenericOutputReader import *
    
class AbinitOutputReader(GenericOutputReader):
    """Read the contents of a directory containing Abinit input and output files
       Inherit the following from the GenericOutputReader
       __init__
       printInfo
       _ReadOutputFile
"""

    def __init__(self, filenames):
        GenericOutputReader.__init__(self,filenames)
        self.type = 'Abinit output files'
        return

    def _ReadOutputFiles(self):
        """Read the Abinit file names"""
        # Define the search keys to be looked for in the files
        self.manage = {}   # Empty the dictionary matching phrases
        self.manage['dynamical']  = (re.compile('  Dynamical matrix,'),self._read_dynamical)
        self.manage['bornCharges']  =  (re.compile('  Effective charges,'),self._read_born_charges)
        self.manage['epsilon']  = (re.compile('  Dielectric tensor,'),self._read_epsilon)
        self.manage['masses']   = (re.compile('              amu '),self._read_masses)
        self.manage['nions']    = (re.compile('            natom '),self._read_natom)
        self.manage['lattice']  = (re.compile('            rprim '),self._read_lattice_vectors)
        self.manage['typat']    = (re.compile('            typat '),self._read_typat)
        self.manage['ntypat']   = (re.compile('           ntypat '),self._read_ntypat)
        self.manage['acell']    = (re.compile('            acell '),self._read_acell)
        for f in self._outputfiles:
            self._ReadOutputFile(f)
        return

    def _read_acell(self,line):
        self.acell = [ float(f)/angs2bohr for f in line.split()[1:4] ]
        return

    def _read_ntypat(self,line):
        self.ntypat = int(line.split()[1])
        return

    def _read_typat(self,line):
        # typat occurs last in the list of data items we need from the output file
        typat = [ int(i) for i in line.split()[1:] ]
        self.masses = [ None for i in range(self.nions) ]
        for i,a in enumerate(typat):
            self.masses[i] = self.typmasses[a-1]
        return

    def _read_epsilon(self,line):
        for i in range(3):
            linea = self.fd.readline().split()
        nlines = 9
        for i in range(nlines):
            linea = self.fd.readline().split()
            if not linea:
                linea = self.fd.readline().split()
            j = int(linea[0])
            k = int(linea[2])
            self.zerof_optical_dielectric[j-1][k-1] = float(linea[4])
        return

    def _read_natom(self,line):
        self.nions = int( line.split()[1] )
        # We can only create this once we know the number of ions
        self.charges = np.zeros( (self.nions,3,3) )
        return

    def _read_masses(self,line):
        self.typmasses = [float(f) for f in line.split()[1:] ]
        return

    def _read_dynamical(self,line):
        # Read the dynamical matrix
        nmodes = self.nions*3
        hessian=np.zeros( (nmodes,nmodes) )
        for i in range(4):
            line = self.fd.readline()
        nlines = nmodes*nmodes
        for i in range(nlines):
            linea = self.fd.readline().split()
            if not linea: 
                linea = self.fd.readline().split()
            diri  = int(linea[0])
            atomi = int(linea[1])
            dirj  = int(linea[2])
            atomj = int(linea[3])
            ipos  = (atomi - 1)*3 + diri -1
            jpos  = (atomj - 1)*3 + dirj -1
            # store the massweighted matrix
            hessian[ipos][jpos] = float(linea[4])/(amu*math.sqrt(self.masses[atomi-1]*self.masses[atomj-1]))
        # symmetrise, project diagonalise and store frequencies and normal modes
        self._DynamicalMatrix(hessian)
        return
 
    def _read_born_charges(self,line):
        """Read the born charges from the outputfile file.  
           Each row of the output refers to a given field direction
           Each column in the row refers the atomic displacement 
           so the output is arranged [ [ a1x a1y a1z ] 
                                       [ a2x a2y a2z ] 
                                       [ a3x a3y a3z ]]
           where 1,2,3 are the field directions and x, y, z are the atomic displacements"""
        for i in range(5): line = self.fd.readline()
        #  The charges are calculated in two ways, we take the mean of the phonon and the field
        nlines = 9*self.nions
        for i in range(nlines):
          linea = self.fd.readline().split()
          if not linea:
              linea = self.fd.readline().split()
          if int(linea[3]) > self.nions:
             ifield = int(linea[2])
             ixyz   = int(linea[0])
             iatom  = int(linea[1])
          else:
             ifield = int(linea[0])
             ixyz   = int(linea[2])
             iatom  = int(linea[3])
          self.charges[iatom-1][ifield-1][ixyz-1] += 0.5*float(linea[4])
        # Convert the charges
        self.born_charges = []
        for i in range(self.nions):
            atom = []
            for ifield in range(3):
                b = self.charges[i][ifield][:].tolist()
                atom.append(b)
            self.born_charges.append(atom)
        if self.neutral:
            self._BornChargeSumRule()
        return

    def _read_lattice_vectors(self,line):
        linea = line.split()
        aVector = [ float(linea[1]), float(linea[2]), float(linea[3]) ]
        linea = self.fd.readline().split()
        bVector = [ float(linea[0]), float(linea[1]), float(linea[2]) ]
        linea = self.fd.readline().split()
        cVector = [ float(linea[0]), float(linea[1]), float(linea[2]) ]
        aVector = [ f * self.acell[0] for f in aVector]
        bVector = [ f * self.acell[1] for f in bVector]
        cVector = [ f * self.acell[2] for f in cVector]
        self.unitCells.append(UnitCell(aVector, bVector, cVector))
        self.ncells = len(self.unitCells)
        self.volume = self.unitCells[-1].volume
        return

