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
"""Read the VASP OUTCAR and other files"""
import string
import re
import cmath
import numpy as np
import scipy as sc
import scipy.optimize as scopt
import math 
import os, sys
from Python.Constants import *
from Python.UnitCell import *

class DielectricConstant:
    """Calculate the dielectric response using the output from vasp"""

    def __init__(self):
        self.unit = self.tensorInitialiseDiagonal( [1.0, 1.0, 1.0] )
        self.reader   = ""
        self.efield_dictionary = {}

    def setReader( self, reader) :
        '''Set the reader to reader.  Either a castep reader or a vasp reader'''
        self.reader = reader
        return 

    def tensorInitialiseDiagonal( self, reals) :
        '''Initialise a 3x3 tensor, the argument is a list of 3 real numbers for the diagonals, the returned tensor is an array'''
        x = np.zeros( (3,3), dtype=np.float)
        x[0,0] = reals[0]
        x[1,1] = reals[1]
        x[2,2] = reals[2]
        return x

    def tensorInitialiseRandom( self, scale ) :
        '''Initialise a 3x3 complex tensor, the argument gives the maximum absolute value'''
        print >> sys.stderr, "Error tensorInitialiseRandom not working"
        exit(1)
        return

    def initialiseSphereDepolarisationMatrix( self ) :
        '''Initialise a 3x3 tensor with the sphere depolarisation matrix, returns a tensor'''
        athird = 1.0 / 3.0
        tensor = self.tensorInitialiseDiagonal( [athird, athird, athird] )
        tensor = tensor / np.trace(tensor)
        return tensor

    def initialisePlateDepolarisationMatrix( self, normal ) :
        '''Initialise a 3x3 tensor with the plate depolarisation matrix, returns a tensor'''
        normal = normal / np.linalg.norm(normal)
        tensor = np.outer(normal, normal)
        tensor = tensor / np.trace(tensor)
        return tensor

    def initialiseNeedleDepolarisationMatrix( self, unique ) :
        '''Initialise a 3x3 tensor with the needle depolarisation matrix'''
        # unique is the unique direction of the needle
        # depolarisation matrix is therefore half the sum of the 
        # two outer products of the directions perpendicular to it
        unique = unique / np.linalg.norm(unique)
        x =  np.array([ 1, 0, 0 ])
        y =  np.array([ 0, 1, 0 ])
        z =  np.array([ 0, 0, 1 ])
        xdotn = np.dot( x , unique )
        ydotn = np.dot( y , unique )
        zdotn = np.dot( z , unique )
        absxdotn = np.abs(xdotn)
        absydotn = np.abs(ydotn)
        abszdotn = np.abs(zdotn)
        # choose the direction with the smallest projection along the needle
        # then project out any needle direction
        if absxdotn <= absydotn and absxdotn <= abszdotn :
           dir1 = x - ( xdotn * unique )
        elif absydotn <= absxdotn and absydotn <= abszdotn :
           dir1 = y - ( ydotn * unique )
        else :
           dir1 = z - ( zdotn * unique )
        dir1 = dir1/np.linalg.norm(dir1)
        # now find the orthogonal direction
        dir2 = np.cross (unique, dir1) 
        dir2 = dir2/np.linalg.norm(dir2)
        # compute the complex tensors from the outer product of each direction
        tensor = np.outer(dir1, dir1) + np.outer(dir2, dir2)
        tensor = tensor / np.trace(tensor)
        return tensor

    def initialiseEllipsoidDepolarisationMatrix( self, unique, aoverb ) :
        '''Initialise a 3x3 tensor with the ellipsoid depolarisation matrix'''
        # unique is the unique direction of the ellipsoid
        # a and b are the sizes of the ellipsoid along the unique axis (a) and perpendicular to it b
        # if a > b then we have a prolate ellipsoid
        cell = self.reader.unitCells[-1]
        unique = unique / np.linalg.norm(unique)
        x =  np.array([ 1, 0, 0 ])
        y =  np.array([ 0, 1, 0 ])
        z =  np.array([ 0, 0, 1 ])
        xdotn = np.dot( x , unique )
        ydotn = np.dot( y , unique )
        zdotn = np.dot( z , unique )
        absxdotn = np.abs(xdotn)
        absydotn = np.abs(ydotn)
        abszdotn = np.abs(zdotn)
        # choose the direction with the smallest projection along the ellipsoid
        # then project out any ellipsoid direction
        if absxdotn <= absydotn and absxdotn <= abszdotn :
           dir1 = x - ( xdotn * unique )
        elif absydotn <= absxdotn and absydotn <= abszdotn :
           dir1 = y - ( ydotn * unique )
        else :
           dir1 = z - ( zdotn * unique )
        dir1 = dir1/np.linalg.norm(dir1)
        # now find the orthogonal direction
        dir2 = np.cross (unique, dir1) 
        dir2 = dir2/np.linalg.norm(dir2)
        bovera = 1.0 / aoverb
        small = 1.0E-8
        if bovera < 1.0-small :
            e = math.sqrt( 1.0  - bovera*bovera )
            Nz = ( 1 - e*e ) * (np.log( ((1+e) / (1-e)) ) - 2*e ) / (2*e*e*e)
        elif bovera > 1.0+small :
            e = math.sqrt( bovera*bovera - 1.0 )
            Nz = ( 1 + e*e ) * (e - np.arctan(e) ) / (e*e*e)
        else :
            Nz = 1.0/3.0
        Nxy = (1 - Nz ) * 0.5
        
        # compute the tensors from the outer product of each direction
        tensor = Nz*np.outer(unique,unique) + Nxy*np.outer(dir1, dir1) + Nxy*np.outer(dir2, dir2)
        #jk print 'Ellipsoid depolarisation tensor'
        #jk print tensor
        tensor = tensor / np.trace(tensor)
        #jk print tensor
        return tensor

    def IonicPermittivity(self, mode_list,oscillator_strengths, frequencies, volume):
        """Calculate the low frequency permittivity or zero frequency permittivity
           oscillator_strengths are in atomic units
           frequencies are in atomic units
           volume is in atomic units"""
        permittivity = np.zeros( (3,3) )
        for imode in mode_list:
           permittivity = permittivity + oscillator_strengths[imode] / ( frequencies[imode] * frequencies[imode] )
        # end for
        return permittivity * ( 4 * PI / volume )
    
    def IRIntensities(self, oscillator_strengths):
        """Calculate the IR intensities from the trace of the oscillator strengths,
           The intensities are returned in units of (D/A)^2/amu"""
        # Each mode has a 3x3 oscillator strength
        nmodes = np.size(oscillator_strengths,0)
        intensities = np.zeros( nmodes )
        for imode,strength in enumerate(oscillator_strengths) :
            # We calculate the intensity from the trace of the strengths
            intensities[imode] = intensities[imode] + strength[0,0] + strength[1,1] + strength[2,2]
        # end for
        maxintensity = np.max(intensities)
        convert = maxintensity
        # convert the intensities to Castep units (D/A)**2/amu
        convert = d2byamuang2
        intensities = intensities / convert
        return intensities
    
    def LongitudinalModes(self, frequencies, normal_modes, born_charges, masses, epsilon_inf, volume, qlist, reader):
        """Apply the nonanalytic correction to the dynamical matrix and calculate the LO frequencies
           frequencies are the frequencies (f) in atomic units
           normal_modes are the mass weighted normal modes (U)
           born_charges are the born charges (Z) stored as 
              [ Z1x Z1y Z1z ] [ Z2x Z2y Z2z ] [ Z3x Z3y Z3z ] ]
              where 1, 2, 3 are the directions of the field and x, y, z are the coordinates of the atom
           qlist is a list of direction vectors
           The subroutine returns a list of (real) frequencies in atomic units
           Any imaginary frequencies are set to 0
           If projection was requested in the reader, the correction is modified ensure translational invariance"""
        # Use a sqrt that returns a complex number
        #from numpy.lib.scimath import sqrt
        # First step is to reconstruct the dynamical matrix (D) from the frequencies and the eigenvectors
        # f^2 = UT . D . U
	# and U is a hermitian matrix so U-1 = UT
        # D = (UT)-1 f^2 U-1 = U f UT
        # Construct UT from the normal modes
	n = np.size(normal_modes,0)
	m = np.size(normal_modes,1)*3
        UT=np.zeros( (n,m) )
        for imode,mode in enumerate(normal_modes) :
           n = 0
           for atom in mode :
                # in python the first index is the row of the matrix, the second is the column
		UT[imode,n+0] = atom[0]
		UT[imode,n+1] = atom[1]
		UT[imode,n+2] = atom[2]
                n = n + 3
           #end for atom
        #end for imode
        Z = born_charges
        # zero the nonanalytical correction
        W  = np.zeros( (n,n) )
        Wm = np.zeros( (n,n) )
        D  = np.zeros( (n,n) )
        # convert the frequencies^2 to a real diagonal array
        # Warning we have to make sure the sign is correct here
        f2 = np.diag( np.sign(frequencies)*np.real(frequencies*frequencies) )
        Dm = np.dot( np.dot(UT.T, f2), UT )
        # Make sure the dynamical matrix is real
        Dm = np.real(Dm)
        # Find its eigenvalues
        eig_val, eig_vec = np.linalg.eigh(Dm)
        # Store the results for returning to the main program
        results = []
        # Loop over q values
        for q in qlist:
            # Now calculate the nonanalytic part
            constant = 4.0 * PI / ( np.dot(np.dot(q, epsilon_inf), q) * volume )
            # Loop over atom a
            for a, Za in enumerate(born_charges):
                # atom is the atom index
                # born contains the polarisability tensor [ z1x z1y z1z ] [ z2x z2y z2z ] [ z3x z3y z3z ] ]
                # where 1, 2, 3 are the directions of the field and x, y, z are the coordinates of the atom
                Za = np.dot(q, Za)
                # Loop over atom b
                for b, Zb in enumerate(born_charges):
                    Zb = np.dot(q, Zb)  
                    terms = np.outer(Za, Zb) * constant / math.sqrt(masses[a]*masses[b])
                    i = a*3
                    for termi in terms:
                        j = b*3
                        for term in termi:
                           Wm[i,j] = term   
                           j = j + 1
                        # end for term
                        i = i + 1
                    #end for i
                # end loop over b
            # end loop over a
            # Construct the full dynamical matrix with the correction
            Dmq = Dm + Wm
            # If projection was requested when the matrix was read, project out translation
            if reader.eckart:
              reader.project(Dmq)
            eig_val, eig_vec = np.linalg.eigh(Dmq)
            # If eig_val less than zero we set it to zero
            values = []
            for eig in eig_val:
                if eig >= 0:
                    val = math.sqrt(eig)
                else:
                    val = -math.sqrt(-eig)
                values.append(val)
            # end of for eig
            # Sort the eigen values in ascending order and append to the results
            results.append(np.sort(values))
        # end loop over q
        return results

    def OscillatorStrengths(self, normal_modes, born_charges):
        """Calculate oscillator strengths from the normal modes and the born charges
           normal_modes are in the mass weighted coordinate system and normalised
           born charges are in electrons, so atomic units"""
        # Each mode has a 3x3 oscillator strength
        nmodes = np.size(normal_modes,0)
        oscillator_strengths = np.zeros( (nmodes,3,3) )
        for imode,mode in enumerate(normal_modes) :
            # We calculate the dipole induced by displacement of each atom along the normal mode
            z_imode = np.zeros(3)
            for atom, born in enumerate(born_charges):
                # atom is the atom index
                # born contains the polarisability tensor [ a1x a1y a1z ] [ a2x a2y a2z ] [ a3x a3y a3z ] ]
                # where 1, 2, 3 are the directions of the field and x, y, z are the coordinates of the atom
                z_imode = z_imode + np.dot( born , mode[atom] ) # the displacement is an array [x, y, z]
            # end for
            # The oscillator strength matrix is the outer product of z
            oscillator_strengths[imode] = np.outer(z_imode, z_imode)
        # end for
        return oscillator_strengths
    
    def NormalModes(self, masses,mass_weighted_normal_modes):
        """ Transform from mass weighted coordinates to xyz. Note this returns an array object.
            The returned normal modes have NOT been renormalised.
            The input masses are in atomic units 
            the output normal modes are in atomic units """
        m = []
        normal_modes = np.zeros_like( mass_weighted_normal_modes )
        nions = np.size(masses)
        for a in range(nions) :
            x = 1.0 / math.sqrt(masses[a])
            atom = [ x, x, x ]
            m.append(atom)
        # end of loop of ions
        array_m = np.array(m)
        for index,mode in enumerate(mass_weighted_normal_modes) :
            normal_modes[index] = mode * array_m
        return normal_modes

    def efield(self, type):
        return np.array(self.efield_dictionary[type])

    def projectField(self,shape,shape_data,projection,efield) :
        """Take the field directions in efield and apply shape projection."""
        if projection == "random" :
            return np.array(efield)
        elif projection == "parallel" :
            if shape == "sphere" :
                return np.array(efield)
            else :
                return np.array(shape_data)
        elif projection == "perpendicular" :
            if shape == "sphere" :
                return np.array(efield)
            else :
                proj_field = []
                data = np.array(shape_data)
                for field in efield :
                    proj = field - ( np.dot(data, field) * data )
                    size = np.linalg.norm(proj_field)
                    if size > 0.0001 :
                        proj_field.append(proj)
                    # end if
                # end for
                return np.array(proj_field)
        else :
            print >> sys.stderr, "Error in projectField, projection unkown: ",projection
            exit(1)
        return

    def rodriguesRotations(self,efield) :
        """Take the field directions in efield and use each direction to calculate a random rotation about that axis.
           Use the field (which a random unit vector in xyz space) to generate an orthogonal rotation matrix
           Rodrigues rotation formula A = I3. cos(theta) + (1-cos(theta)) e . eT + ex sin(theta0
           I3 is a unit matrix
           e is the direction
           ex is the cross product matrix 
           ( 0  -e3   e2 )
           ( e3  0   -e1 )
           (-e2  e1   0  )
           Input field is real
           Output is a list of rotations
"""
        rotations = []
        for field in efield :
            # Calculate a random angle between 0 and 180
            theta = PI*np.random.rand() 
            cos   = np.cos(theta)
            sin   = np.sin(theta)
            rotation = np.zeros( (3,3) )
            e1 = field[0]
            e2 = field[1]
            e3 = field[2]
            rotation[0,0] = cos + (1-cos)*e1*e1
            rotation[0,1] =       (1-cos)*e2*e1 + sin*e3
            rotation[0,2] =       (1-cos)*e3*e1 - sin*e2
            rotation[1,0] =       (1-cos)*e1*e2 - sin*e3
            rotation[1,1] = cos + (1-cos)*e2*e2 
            rotation[1,2] =       (1-cos)*e3*e2 + sin*e1
            rotation[2,0] =       (1-cos)*e1*e3 + sin*e2
            rotation[2,1] =       (1-cos)*e2*e3 - sin*e1
            rotation[2,2] = cos + (1-cos)*e3*e3 
            #jk test = np.dot(rotation.T,rotation)
            #jk print "This array should be unit", test
            rotations.append(rotation)
        return rotations


    def absorptionFromModeIntensities(self,f,modes,frequencies,sigmas,intensities) :
        """Calculate the absorption from the frequencies and intensities using a Lorentzian
           f is the frequency of the absorption in cm-1
           modes are a list of the modes
           frequencies(cm-1), sigmas(cm-1) and intensities (D2/A2/amu) 
           The number 4225.6 converts the units of D2/A2/amu to L mole-1 cm-1 cm-1
           The output from this is the molar absorption coefficient at f, in L/mol/cm"""
        absorption = 0.0
        for mode in modes:
            v = np.real(frequencies[mode])
            sigma = sigmas[mode]
            icastep = intensities[mode]
            absorption = absorption + 2.0 * 4225.6 * icastep / PI * ( sigma / ( 4.0 * (f - v )*(f - v) + sigma*sigma) )
        return absorption
            
    def dielectricContribution(self,f,modes,frequencies,sigmas,strengths,volume) :
        """Calculate the dielectric function for a set of modes with their own widths and strengths
           f is the frequency of the dielectric response in au
           modes are a list of the modes
           frequencies(au), sigmas(au) and strengths(au) are fairly obvious
           The output from this calculation is a complex dielectric tensor"""
        dielectric = np.zeros( (3,3) , dtype=complex)
        for mode in modes:
            v = frequencies[mode]
            sigma = sigmas[mode]
            s = strengths[mode].astype(complex)
            dielectric = dielectric + s / np.complex( (v*v - f*f), -sigma*f )
        return dielectric * (4.0*PI/volume)
            
    def drudeContribution(self,f,frequency,sigma,volume) :
        """Calculate the dielectric function for a set of a Drude oscillator
           f is the frequency of the dielectric response in au
           frequency(au), sigmas(au) are the plasma frequency and the width
           The output from this calculation is a complex dielectric tensor"""
        dielectric = np.zeros( (3,3) , dtype=complex)
        # Avoid a divide by zero if f is small
        if f <= 1.0e-8:
            f = 1.0e-8
        # Assume that the drude contribution is isotropic
        dielectric = dielectric - self.unit * frequency*frequency / np.complex( -f*f , -sigma*f )
        return dielectric * (4.0*PI/volume)
            

    def averagedPermittivity(self,dielectric_medium,dielecv,shape,L,vf) :
        """Calculate the effective constant permittivity using the averaged permittivity method
           dielectric_medium is the dielectric constant tensor of the medium
           dielecv is the total frequency dielectric constant tensor at the current frequency
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           The routine returns the effective dielectric constant"""
        effd = vf * dielecv + (1.0-vf) * dielectric_medium
        trace = np.trace(effd) / 3.0
        effdielec = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return effdielec 

    def balan(self,dielectric_medium,dielecv,shape,L,vf) :
        """Calculate the effective constant permittivity using the method of balan
           dielectric_medium is the dielectric constant tensor of the medium
           dielecv is the total frequency dielectric constant tensor at the current frequency
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           The routine returns the effective dielectric constant"""
        dielecvm1 = (dielecv - self.unit) 
        deformation  = np.dot( dielectric_medium, np.linalg.inv( dielectric_medium + np.dot( L , (dielecv - dielectric_medium)) ) )
        effd          = self.unit + np.dot(deformation, dielecvm1)
        trace = vf * np.trace(effd) / 3.0  
        effdielec = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return effdielec 

    def maxwell(self,dielectric_medium,dielecv,shape,L,vf) :
        """Calculate the effective constant permittivity using the maxwell garnett method 
           dielectric_medium is the dielectric constant tensor of the medium
           dielecv is the total frequency dielectric constant tensor at the current frequency
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           vf is the volume fraction of filler
           The routine returns the effective dielectric constant"""
        emedium = np.trace(dielectric_medium) / 3.0
        # Equation 5.78 in Sihvola
        nalpha = emedium*vf*np.dot((dielecv - dielectric_medium),np.linalg.inv(dielectric_medium + np.dot(L, (dielecv-dielectric_medium))))
        nalphaL = np.dot((nalpha/emedium),L)
        # average the polarisability over orientation
        nalpha = np.trace(nalpha) / 3.0 * self.unit
        # average the polarisability*L over orientation
        nalphaL = np.trace(nalphaL) / 3.0 * self.unit
        polarisation = np.dot(np.linalg.inv(self.unit - nalphaL), nalpha)
        effd         = dielectric_medium + polarisation
        trace = np.trace(effd) / 3.0
        effdielec = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return effdielec 
            
            
    def maxwell_sihvola(self,dielectric_medium,dielecv,shape,L,vf) :
        """Calculate the effective constant permittivity using the maxwell garnett method 
           dielectric_medium is the dielectric constant tensor of the medium
           dielecv is the total frequency dielectric constant tensor at the current frequency
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           vf is the volume fraction of filler
           The routine returns the effective dielectric constant"""
        # Equation 6.29 on page 123 of Sihvola
        # Equation 6.40 gives the averaging over the orientation function
        # See also equation 5.80 on page 102 and equation 4.31 on page 70
        Me = dielectric_medium
        # assume that the medium is isotropic calculate the inverse of the dielectric
        Mem1 = 3.0 / np.trace(Me)
        Mi = dielecv
        # calculate the polarisability matrix x the number density of inclusions
        nA = vf*np.dot( (Mi-Me), np.linalg.inv( self.unit + (Mem1 * np.dot(L, (Mi - Me)))))
        nAL = np.dot((nA),L)
        # average the polarisability over orientation
        nA = np.trace(nA) / 3.0 * self.unit
        # average the polarisability*L over orientation
        nAL = np.trace(nAL) / 3.0 * Mem1 * self.unit
        # Calculate the average polarisation factor which scales the average field 
        # based on equation 5.80
        # <P> = pol . <E>
        pol = np.dot(np.linalg.inv(self.unit - nAL), nA)
        # Meff . <E> = Me . <E> + <P>
        # Meff . <E> = Me. <E> + pol . <E>
        # Meff = Me + pol
        effd         = dielectric_medium + pol
        # Average over orientation
        trace = np.trace(effd) / 3.0 
        effdielec = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return effdielec 
            
    def coherent(self,dielectric_medium,dielecv,shape,L,vf,dielectric_apparent) :
        for i in range(10):
            dielectric_apparent = 0.1 * dielectric_apparent + 0.9 * self.coherent2(dielectric_medium,dielectric_apparent,dielecv,shape,L,vf) 
        return dielectric_apparent

    def coherent2(self,dielectric_medium,dielectric_apparent,dielecv,shape,L,vf) :
        """Calculate the effective constant permittivity using the maxwell garnett method 
           dielectric_medium is the dielectric constant tensor of the medium
           dielecv is the total frequency dielectric constant tensor at the current frequency
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           vf is the volume fraction of filler
           The routine returns the effective dielectric constant"""
        emedium = np.trace(dielectric_medium) / 3.0
        eapparent = np.trace(dielectric_apparent) / 3.0
        # Equation 5.78 in Sihvola
        nalpha = emedium*vf*np.dot((dielecv - dielectric_medium),np.linalg.inv(dielectric_medium + np.dot(L, (dielecv-dielectric_medium))))
        nalphaL = np.dot((nalpha/eapparent),L)
        # average the polarisability over orientation
        nalpha = np.trace(nalpha) / 3.0 * self.unit
        # average the polarisability*L over orientation
        nalphaL = np.trace(nalphaL) / 3.0 * self.unit
        polarisation = np.dot(np.linalg.inv(self.unit - nalphaL), nalpha)
        effd         = dielectric_medium + polarisation
        trace = np.trace(effd) / 3.0
        effdielec = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return effdielec 
            
    def bruggeman_minimise(self,eps1,eps2,shape,L,f2,epsbr) :
        """Calculate the effective constant permittivity using the method of bruggeman
           eps1 is the dielectric constant tensor of 1 (The medium)
           eps2 is the dielectric constant tensor of 2 (The inclusion)
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           f2 is the volume fraction of component 2
           epsbr is an initial guess at the solution
           The routine returns the effective dielectric constant
           On the application of homogenization formalisms to active dielectric composite materials
           Tom G. Mackay, Akhlesh Lakhtakia """
        f1 = 1.0 - f2
        # we need to fool the optimiser into thinking that it has two real variables
        # in fact the second is imaginary and reconstructed in the _brug_minimise routine
        trace = np.trace(epsbr) / 3.0
        variables = np.array( [np.real(trace),np.log(1.0 + np.abs(np.imag(trace)))] )
        options = { 'xtol' : 1.0e-4,
                    'ftol' : 1.0E-4 }
        sol = sc.optimize.minimize(self._brug_minimise_tensor,variables,method='Powell',args=(eps1,eps2,shape,L,f1),options=options)
        if not sol.success:
            print "A Bruggeman solution was not found at this frequency"
        variables = sol.x
        # transform the imaginary variable back
        trace = complex(variables[0],np.exp(variables[1])-1.0)
        epsbr = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return epsbr 

    def bruggeman_iter(self,eps1,eps2,shape,L,f2,epsbr) :
        """Calculate the effective constant permittivity using the method of bruggeman
           eps1 is the dielectric constant tensor of 1 (The medium)
           eps2 is the dielectric constant tensor of 2 (The inclusion)
           shape is the name of the current shape
           L is the shapes depolarisation matrix
           f2 is the volume fraction of component 2
           epsbr is an initial guess at the solution
           The routine returns the effective dielectric constant
           On the application of homogenization formalisms to active dielectric composite materials
           Tom G. Mackay, Akhlesh Lakhtakia """
        f1 = 1.0 - f2
        # perform an iteration
        converged = False
        niters = 0
        while not converged:
            niters += 1
            epsbr,error = self._brug_iter_error(epsbr,eps1,eps2,shape,L,f1)
            # print "Bruggeman"
            # print "epsbr = ",epsbr
            # print "error = ",niters,error
            if abs(error) < 1.0E-8 :
                converged = True
            if niters > 3000:
                print "Bruggeman iterations failed, error=", error
                converged = True
        epsbr = self.average_tensor(epsbr)
        return epsbr

    def average_tensor(self,t):
        a = np.trace(t) / 3.0
        return np.array ( [ [a, 0, 0], [ 0, a, 0] , [0, 0, a]] )

    def _brug_minimise_scalar(self,variables,eps1,eps2,shape,L,f1) :
        # unpack the complex number from the variables
        # two things going on here. 
        # 1. the two variables refer to the real and imaginary components
        # 2. we require the imaginary component to be positive
        trace = complex(variables[0],np.exp(variables[1])-1.0)
        epsbr = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        f2 = 1.0 - f1
        b1 = np.dot(L,(eps1 - epsbr))
        b2 = np.dot(L,(eps2 - epsbr))
        tb1 = np.trace(b1)/3.0
        tb2 = np.trace(b2)/3.0
        ta1 = 1.0/ ( 1.0 + tb1 )
        ta2 = 1.0/ ( 1.0 + tb2 )
        c1 = eps1-epsbr
        c2 = eps2-epsbr
        tc1 = np.trace(c1)/3.0
        tc2 = np.trace(c2)/3.0
        # alpha1 and 2 are the polarisabilities of 1 and 2 in the effective medium 
        talpha1 = tc1 * ta1
        talpha2 = tc2 * ta2
        error = f1*talpha1 + f2*talpha2
        error = np.abs(error.conjugate() * error)
        # Nasty issue in the powell method, the convergence on tol is given
        # relative to the solution (0.0).  Only a small number is added.
        # So we shift the solution by 1.0, the tol is now relative to 1.0
        return 1.0+error
        
    def _brug_minimise_tensor(self,variables,eps1,eps2,shape,L,f1) :
        # unpack the complex number from the variables
        # two things going on here. 
        # 1. the two variables refer to the real and imaginary components
        # 2. we require the imaginary component to be positive
        trace = complex(variables[0],np.exp(variables[1])-1.0)
        epsbr = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        f2 = 1.0 - f1
        b1 = np.dot(L,(eps1 - epsbr))
        b2 = np.dot(L,(eps2 - epsbr))
        b1 = self.average_tensor(b1)
        b2 = self.average_tensor(b2)
        a1 = np.linalg.inv( epsbr + b1 )
        a2 = np.linalg.inv( epsbr + b2 )
        c1 = eps1-epsbr
        c2 = eps2-epsbr
        # c1 = self.average_tensor( eps1-epsbr )
        # c2 = self.average_tensor( eps2-epsbr )
        alpha1 = np.dot( c1, a1)
        alpha2 = np.dot( c2, a2)
        alpha1 = self.average_tensor( alpha1 )
        alpha2 = self.average_tensor( alpha2 )
        error = f1*alpha1 + f2*alpha2
        fr  = 0.0
        fi  = 0.0
        for c in error:
           for f in c:
              fr += np.real(f)**2
              fi += np.imag(f)**2
        error = np.linalg.norm(error)
        # Nasty issue in the powell method, the convergence on tol is given
        # relative to the solution (0.0).  Only a small number is added.
        # So we shift the solution by 1.0, the tol is now relative to 1.0
        return 1.0+error
        
            
    def _brug_iter_error(self,epsbr,eps1,eps2,shape,L,f1) :
        f2 = 1.0 - f1
        Leps1 = np.dot(L, (eps1 - epsbr))
        Leps2 = np.dot(L, (eps2 - epsbr))
        Leps1 = self.average_tensor(Leps1)
        Leps2 = self.average_tensor(Leps2)
        a1 = np.linalg.inv( epsbr + Leps1 )
        a2 = np.linalg.inv( epsbr + Leps2 )
        # alpha1 and 2 are the polarisabilities of 1 and 2 in the effective medium 
        eps1av = self.average_tensor(eps1)
        eps2av = self.average_tensor(eps2)
        alpha1 = np.dot( (eps1av-epsbr), a1)
        alpha2 = np.dot( (eps2av-epsbr), a2)
        # the error or residual matrix should be zero for a bruggeman solution
        error = f1*alpha1 + f2*alpha2
        error = np.linalg.norm(error)
        m1 = f1*np.dot(eps1,a1)+f2*np.dot(eps2,a2)
        m2 = np.linalg.inv(f1*a1 + f2*a2)
        epsbr = np.dot(m1,m2) 
        trace = np.trace(epsbr) / 3.0
        epsbr = np.array ( [ [trace, 0, 0], [0,trace,0], [0,0,trace] ] )
        return epsbr,error
        
            
    def refractive_index(self,dielectric,debug=False) :
        ''' Calculate the refractive index from the dielectric constant.  
            Calculate the trace of the dielectric and calculate both square roots.
            The choose the root with the largest imaginary component This obeys the Konig Kramer requirements'''
        trace = np.trace(dielectric)/3.0
        sq1 = np.sqrt(trace)
        r,phase = cmath.polar(sq1)
        sq2 = cmath.rect(-r,phase)
        imag1 = np.imag(sq1)
        imag2 = np.imag(sq2)
        if imag1 > imag2:
            sq = sq1
        else:
            sq = sq2
        if np.abs(sq*sq-trace)/(1+np.abs(trace)) > 1.0E-8 or debug :
            print "There is an error in refractive index"
            print "trace = ", trace
            print "sq*sq = ", sq*sq, np.abs(sq*sq-trace)
            print "sq    = ", sq , sq*sq
            print "sq1   = ", sq1, sq1*sq1
            print "sq2   = ", sq2, sq2*sq2
        return sq 

    def directionFromShape(self, data) :
        # Determine the unique direction of the shape from data
        # data may contain a miller indices which defines a surface eg. (1,1,-1)
        # or a direction as a miller direction vector eg. [1,0,-1]
        surface = False
        original = data
        i = data.find(",")
        commas=False
        if i >= 0:
            commas=True
        if data[0] == "{":
            surface = True
            data = data.replace("{","")
            data = data.replace("}","")
        elif data[0] == "(":
            surface = True
            data = data.replace("(","")
            data = data.replace(")","")
        elif data[0] == "[":
            surface = False
            data = data.replace("[","")
            data = data.replace("]","")
        else:
            print "Error encountered in interpretting the miller surface / vector", data
            exit(1)
        if commas:
            data = data.replace(",", " ")
            hkl = ( [ int(f) for f in data.split() ] )
        else:
            i = 0
            hkl = [0, 0, 0]
            for k in [ 0, 1, 2 ]:
              sign = 1
              if data[i] == "-":
                  i += 1
                  sign = -1
              hkl[k] =  sign * int(data[i])
              i += 1
        # end of handling no commas
        if not len(hkl) == 3:
            print "Error encountered in interpretting the miller surface / vector", data
            exit(1)
        cell = self.reader.unitCells[-1]
        if surface:
            direction = cell.convertHkl2Xyz(hkl)
        else:
            direction = cell.convertAbc2Xyz(hkl)
        direction = direction / np.linalg.norm(direction)
        data = data.replace('"','')    
        data = data.replace("",'') 
        if surface:
            print "The miller indices for the surface ", original, "has a normal", direction, "in xyz"
        else:
            print "The miller direction ", original, "is ", direction, "in xyz"
        return direction


